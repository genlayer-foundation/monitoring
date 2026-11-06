local lib = require("lib-genvm")
local llm = require("lib-llm")
local llm_policy = require("llm_policy")
local sqlite3 = require("lsqlite3")

-- There is no guarantee that different genvm executions will be executed in the same lua VM.
-- Moreover, multiple genvms can be executed in parallel, so avoid using global state.
-- Instead, each genvm creates a session, which has a single `ctx` object,
-- which is preserved across multiple calls

--- GEN-wei charged per token, before rounding the total charge.
---@param ctx any execution context
---@param provider string provider id
---@param model string model name
---@return Rat GEN-wei charged per token
local function gen_per_token(ctx, provider, model)
	local meta = llm.providers[provider].models[model].meta
	local rate = meta and meta.time_units_per_1k_tokens
	if rate == nil then
		rate = "1/4"
	end
	assert(type(rate) == "string", "time_units_per_1k_tokens must be a rational string")
	rate = rat.new(rate)
	assert(rate >= rat.zero, "time_units_per_1k_tokens must be non-negative")
	return (ctx.gen_per_time_unit or rat.zero) * rate / rat.new(1000)
end

local function get_or_create_stats(ctx, provider, model)
	local key = provider .. "/" .. model
	local entry = ctx.stats[key]
	if entry == nil then
		entry = {
			error_count = 0,
			input_tokens = 0,
			output_tokens = 0,
			total_tokens = 0,
			cache_read_tokens = 0,
			cache_write_tokens = 0,
			image_units = 0,
		}
		ctx.stats[key] = entry
	end
	return entry
end

---@param request { prompt: Prompt, format: Format, model: string, provider: string, timeout: number | nil }
---@param calc_consumed_gen fun(res: ProviderResult): Rat | number | nil
---@return ProviderResult
local function exec_update_policy_data(ctx, request, calc_consumed_gen)
	local success, res = pcall(llm.rs.exec_prompt_in_provider, ctx, request)

	local entry = get_or_create_stats(ctx, request.provider, request.model)

	if success then
		local consumed_gen = calc_consumed_gen(res)
		if consumed_gen then
			ctx.policy.spent_gen_wei = ctx.policy.spent_gen_wei + rat.new(consumed_gen)
		end
		if ctx.policy.stop_on_spent and ctx.policy.spent_gen_wei >= ctx.policy.stop_on_spent then
			ctx.policy.exhausted = true
		end

		local t = res.tokens
		if t then
			entry.input_tokens = entry.input_tokens + (t.input or 0)
			entry.output_tokens = entry.output_tokens + (t.output or 0)
			entry.total_tokens = entry.total_tokens + (t.total or 0)
			entry.cache_read_tokens = entry.cache_read_tokens + (t.cache_read or 0)
			entry.cache_write_tokens = entry.cache_write_tokens + (t.cache_write or 0)
			entry.image_units = entry.image_units + (t.image_units or 0)
		end
		return res
	else
		entry.error_count = entry.error_count + 1

		error(res)
	end
end

-- ---------------------------------------------------------------------------
-- Per-call telemetry (Foundation node, 2026-11-03). One JSON line per provider
-- attempt and one per prompt, appended to a file Alloy already ships to Loki
-- (LOG_FILE_PATTERN=/var/log/genlayer/node*.log). Feeds the Grafana board
-- "GenLayer Foundation | LLM Providers". Strictly best-effort: every write is
-- wrapped in pcall, so telemetry can never fail or slow down a prompt.
-- NOTE: this file is overwritten by node upgrades — re-apply after each one.
-- ---------------------------------------------------------------------------
local CALL_LOG = "/opt/genlayer-node/data/node/logs/node-llm-calls.log"
local CALL_LOG_MAX_BYTES = 50 * 1024 * 1024
local CALL_LOG_KEYS = {
	"time", "event", "tx_id", "session", "lead", "attempt", "fallback",
	"provider", "model", "format", "images", "ok", "ms", "timeout_s",
	"http_status", "error_kind", "error", "attempts", "providers_tried",
	"tokens_in", "tokens_out", "tokens_total", "cost_usd",
}

local JSON_ESCAPES = { ['"'] = '\\"', ["\\"] = "\\\\", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }

local function json_value(v)
	local t = type(v)
	if t == "string" then
		local s = v:gsub('[%c"\\]', function(c)
			return JSON_ESCAPES[c] or string.format("\\u%04x", c:byte())
		end)
		return '"' .. s .. '"'
	elseif t == "number" then
		if v ~= v or v == math.huge or v == -math.huge then
			return "null"
		end
		if v == math.floor(v) and math.abs(v) < 2 ^ 53 then
			return string.format("%d", v)
		end
		return string.format("%.10g", v)
	elseif t == "boolean" then
		return tostring(v)
	end
	return nil
end

local function emit_call_log(fields)
	pcall(function()
		fields.time = os.date("!%Y-%m-%dT%H:%M:%SZ")
		local parts = {}
		for _, k in ipairs(CALL_LOG_KEYS) do
			local enc = fields[k] ~= nil and json_value(fields[k]) or nil
			if enc ~= nil then
				parts[#parts + 1] = '"' .. k .. '":' .. enc
			end
		end
		local line = "{" .. table.concat(parts, ",") .. "}\n"

		local f = io.open(CALL_LOG, "a")
		if not f then
			return
		end
		local size = f:seek("end")
		if size and size > CALL_LOG_MAX_BYTES then
			-- ".1" does not match node*.log, so Alloy will not re-ship it
			f:close()
			os.rename(CALL_LOG, CALL_LOG .. ".1")
			f = io.open(CALL_LOG, "a")
			if not f then
				return
			end
		end
		f:write(line)
		f:close()
	end)
end

local function short_error(s)
	s = tostring(s or "")
	if #s > 300 then
		s = s:sub(1, 300)
	end
	return s
end

local MAX_BUDGET_TIMEOUT = rat.new("60")

local function compute_timeout(ctx, remaining_gen)
	if ctx.gen_per_time_unit == nil then
		return nil
	end
	local timeout = remaining_gen / ctx.gen_per_time_unit * rat.new("3/2")
	if timeout <= rat.zero or timeout > MAX_BUDGET_TIMEOUT then
		return nil
	end
	return timeout:to_float()
end

-- llm_policy owns backend selection and the failure state machine; this script
-- keeps transport, gen accounting, stats, timeouts and the error contract.
--
-- The catalog keys a model by "<provider>/<model>", not the bare model name: two
-- backends may serve the same name with different capabilities, and one key
-- would let one backend's capabilities vouch for another's. The chain reproduces
-- the pre-engine ordering: priority desc, provider name desc, model name asc.
local PROFILE_NAME = "compat"

local function build_policy_config()
	local providers = {}
	local models = {}
	local chain = {}

	local provider_names = {}
	for provider_name, _ in pairs(llm.providers) do
		table.insert(provider_names, provider_name)
	end

	table.sort(provider_names, function(a, b)
		local a_meta = llm.providers[a].meta
		local b_meta = llm.providers[b].meta
		local a_priority = a_meta and a_meta.priority or 0
		local b_priority = b_meta and b_meta.priority or 0

		if a_priority ~= b_priority then
			return a_priority > b_priority
		end
		return a > b -- just compare names
	end)

	for _, provider_name in ipairs(provider_names) do
		local provider_data = llm.providers[provider_name]

		-- Placeholders: the engine validates these but never dereferences them;
		-- host and key stay in Rust.
		providers[provider_name] = {
			base_url = "managed-by-genvm",
			api_kind = "openai_compatible",
			auth_env = "managed-by-genvm",
			tier = "partner",
			discovery = "static",
		}

		local model_names = {}
		for model_name, _ in pairs(provider_data.models or {}) do
			table.insert(model_names, model_name)
		end
		table.sort(model_names)

		for _, model_name in ipairs(model_names) do
			local model_data = provider_data.models[model_name]
			local family = provider_name .. "/" .. model_name

			models[family] = {
				served_by = {
					{ provider = provider_name, provider_model_id = model_name },
				},
				capabilities = {
					supports_json_mode = model_data.supports_json or false,
					supports_vision = model_data.supports_image or false,
					supports_seed = true,
				},
			}

			table.insert(chain, { provider = provider_name, model = family })
		end
	end

	return {
		providers = providers,
		models = models,
		profiles = {
			[PROFILE_NAME] = {
				selector = "chain",
				chain = chain,
				retry_policy = PROFILE_NAME,
			},
		},
		-- Every failure kind falls through to the next candidate, preserving the
		-- pre-engine behaviour of retrying on any user error, overloaded or not.
		retry_policies = {
			[PROFILE_NAME] = {
				unknown = { action = "next_candidate" },
			},
		},
	}
end

-- The engine reads `host` as a plain global. Omitting `call_provider`/`sleep_ms`
-- keeps its blocking driver unreachable: this script drives execute_step itself.
_G.host = {
	now_ms = function()
		return lib.rs.monotonic_ms()
	end,
	log = function(level, event, fields, audience)
		lib.log { level = level, message = event, fields = fields, audience = audience }
	end,
}

local POLICY_CONFIG = build_policy_config()

-- Rotation: these providers lead the chain in an order picked per session from
-- the random policy seed, so load splits evenly between them; each one falls
-- back to the other, then to the rest of the compat chain. A provider that is
-- ineligible for a prompt (e.g. no json support) is skipped by the engine.
local ROTATE = { "unhardcoded", "morpheus", "pearl" }

local function rotated_config(seed)
	local cfg = build_policy_config()
	local chain = cfg.profiles[PROFILE_NAME].chain
	local n = #ROTATE
	local first = (seed % n) + 1
	local head, rest = {}, {}
	for i = 0, n - 1 do
		local p = ROTATE[((first - 1 + i) % n) + 1]
		for _, entry in ipairs(chain) do
			if entry.provider == p then
				table.insert(head, entry)
			end
		end
	end
	for _, entry in ipairs(chain) do
		local rotated = false
		for _, p in ipairs(ROTATE) do
			if entry.provider == p then
				rotated = true
			end
		end
		if not rotated then
			table.insert(rest, entry)
		end
	end
	for _, entry in ipairs(rest) do
		table.insert(head, entry)
	end
	cfg.profiles[PROFILE_NAME].chain = head
	return cfg, ROTATE[first]
end

do
	-- Reject a bad catalog at module start, not on the first prompt.
	local ok, err = llm_policy.init(POLICY_CONFIG)
	if not ok then
		error("llm_policy rejected the generated catalog: " .. tostring(err))
	end
end

--- Describe a mapped prompt to the engine: which capabilities a candidate must
--- have to be eligible. Mirrors the checks `llm.select_providers_for` performs.
---@param mapped_prompt MappedPrompt
---@return table
local function build_contract(ctx, mapped_prompt)
	local needs = {}
	if lib.get_first_from_table(mapped_prompt.prompt.images) ~= nil then
		table.insert(needs, "vision")
	end

	local response_format = nil
	if mapped_prompt.format == "json" or mapped_prompt.format == "bool" then
		-- bool is parsed out of a json object, so it needs json capability too
		response_format = { type = "json_object" }
	end

	return {
		profile = PROFILE_NAME,
		requirements = { needs = needs },
		response_format = response_format,
		seed = ctx.policy_seed,
	}
end

-- Cap on how long a policy-requested backoff may block one prompt.
local MAX_WAIT_SECONDS = 30

-- Run the (provider, model) the engine asked for. Returns the answer on success
-- (nil otherwise) and the feedback table to hand back to `execute_step`. A
-- non-user error is re-raised: it is a runtime fault, not a routing signal.
local function run_candidate(ctx, mapped_prompt, timeout, request, trace)
	local provider_name = request.provider_id
	local model_name = request.served_model_id
	local model_data = llm.providers[provider_name].models[model_name]

	mapped_prompt.prompt.use_max_completion_tokens = model_data.use_max_completion_tokens

	local call = {
		provider = provider_name,
		model = model_name,
		prompt = mapped_prompt.prompt,
		format = mapped_prompt.format,
		timeout = timeout,
	}

	trace.attempt = trace.attempt + 1
	trace.providers_tried[#trace.providers_tried + 1] = provider_name
	local attempt_log = {
		event = "attempt",
		tx_id = ctx.tx_id,
		session = ctx.policy_seed,
		lead = ctx.rotation_lead,
		attempt = trace.attempt,
		fallback = trace.attempt > 1,
		provider = provider_name,
		model = model_name,
		format = mapped_prompt.format,
		images = trace.images,
		timeout_s = timeout,
	}

	lib.log { level = "trace", message = "calling exec_prompt_in_provider", request = call }
	local token_price = gen_per_token(ctx, call.provider, call.model)
	local started_ms = lib.rs.monotonic_ms()
	local success, result = pcall(exec_update_policy_data, ctx, call, function(res)
		-- convert token usage into gen using the per-model rate, and report it
		-- back as the gen consumed by this call (charged to the host as fuel)
		local total_tokens = (res.tokens and res.tokens.total) or 0
		local consumed_gen = (rat.new(total_tokens) * token_price):ceil()
		res.consumed_gen = consumed_gen
		return consumed_gen
	end)
	attempt_log.ms = lib.rs.monotonic_ms() - started_ms

	if success then
		local t = result and result.tokens
		if t then
			attempt_log.tokens_in = t.input
			attempt_log.tokens_out = t.output
			attempt_log.tokens_total = t.total
			local raw = t.raw_usage
			if type(raw) == "table" and type(raw.cost) == "number" then
				attempt_log.cost_usd = raw.cost
			end
		end
		attempt_log.ok = true
		emit_call_log(attempt_log)
		return result, { ok = true }
	end

	local as_user_error = lib.rs.as_user_error(result)
	if as_user_error == nil then
		lib.log { level = "warning", audience = "operator", message = "non-user-error", original = result }
		attempt_log.ok = false
		attempt_log.error_kind = "runtime_error"
		attempt_log.error = short_error(result)
		emit_call_log(attempt_log)
		error(result)
	end

	local status = as_user_error.ctx and as_user_error.ctx.status
	lib.log {
		level = "warning",
		audience = "operator",
		message = "provider failed, looking for next",
		error = as_user_error,
	}

	local error_kind = llm.provider_http_error_description(status)
	local causes = table.concat(as_user_error.causes or {}, ",")
	attempt_log.ok = false
	attempt_log.http_status = status
	attempt_log.error_kind = error_kind
	attempt_log.error = short_error(causes)
	emit_call_log(attempt_log)

	return nil,
		{
			ok = false,
			error_kind = error_kind,
			http_status = status,
			-- the engine stores this as a plain string in its trace
			error_message = causes,
		}
end

-- Sleep out a policy-requested backoff, bounded by MAX_WAIT_SECONDS. `until_ms`
-- is on the same monotonic clock the engine reads through `host.now_ms`.
local function wait_until(until_ms)
	local delay = ((until_ms or 0) - lib.rs.monotonic_ms()) / 1000
	if delay <= 0 then
		return
	end
	lib.log { level = "debug", audience = "operator", message = "policy backoff", seconds = delay }
	lib.rs.sleep_seconds(math.min(delay, MAX_WAIT_SECONDS))
end

local function dispatch_prompt(ctx, mapped_prompt, remaining_gen)
	---@cast mapped_prompt MappedPrompt

	local timeout = compute_timeout(ctx, remaining_gen)
	if timeout and timeout < 1 then
		lib.log {
			level = "warning",
			audience = "user",
			message = "computed timeout is very low, failing immediately",
			timeout = timeout,
		}
		emit_call_log {
			event = "prompt",
			tx_id = ctx.tx_id,
			session = ctx.policy_seed,
			lead = ctx.rotation_lead,
			format = mapped_prompt.format,
			ok = false,
			attempts = 0,
			timeout_s = timeout,
			error_kind = "budget_timeout_too_low",
		}
		llm.exhaust()
	end

	local contract = build_contract(ctx, mapped_prompt)
	local trace = {
		attempt = 0,
		providers_tried = {},
		images = lib.get_first_from_table(mapped_prompt.prompt.images) ~= nil,
	}
	local prompt_started_ms = lib.rs.monotonic_ms()

	lib.log {
		level = "debug",
		message = "executing prompt in backend",
		prompt = mapped_prompt,
		contract = contract,
	}

	local step = llm_policy.execute_step(nil, contract)
	local answer = nil

	while step.status ~= "done" do
		if step.status == "call" then
			local this_answer, feedback = run_candidate(ctx, mapped_prompt, timeout, step.request, trace)
			answer = this_answer or answer
			step = llm_policy.execute_step(step.state_handle, nil, feedback)
		elseif step.status == "wait" then
			wait_until(step.until_ms)
			step = llm_policy.execute_step(step.state_handle, nil, nil)
		else
			error("unexpected policy step status: " .. tostring(step.status))
		end
	end

	local prompt_log = {
		event = "prompt",
		tx_id = ctx.tx_id,
		session = ctx.policy_seed,
		lead = ctx.rotation_lead,
		format = mapped_prompt.format,
		images = trace.images,
		ok = step.result.ok and true or false,
		attempts = trace.attempt,
		fallback = trace.attempt > 1,
		provider = trace.providers_tried[#trace.providers_tried],
		providers_tried = table.concat(trace.providers_tried, ">"),
		ms = lib.rs.monotonic_ms() - prompt_started_ms,
		timeout_s = timeout,
	}

	if step.result.ok then
		emit_call_log(prompt_log)
		return answer
	end

	prompt_log.provider = nil
	prompt_log.error_kind = "no_provider"
	local err = step.result.error
	if type(err) == "table" then
		err = err.kind or err.code or err.message
	end
	prompt_log.error = short_error(err)
	emit_call_log(prompt_log)

	lib.log {
		level = "error",
		audience = "operator",
		message = "no provider could handle prompt",
		error = step.result.error,
		trace = step.result.trace,
	}
	lib.rs.user_error {
		causes = { "NO_PROVIDER_FOR_PROMPT" },
		fatal = true,
		ctx = {
			prompt = mapped_prompt.prompt,
			trace = step.result.trace,
		},
	}
end

function Setup(ctx)
	ctx.stats = {}

	-- Per-session routing seed: true randomness so validators diverge, logged so
	-- the decision can be replayed from the record. Also picks which ROTATE
	-- provider leads this session's chain.
	local host_data = ctx.host_data or {}
	local b1, b2, b3, b4 = string.byte(lib.rs.random_bytes(4), 1, 4)
	ctx.policy_seed = (((b1 * 256 + b2) * 256 + b3) * 256 + b4) % 2147483647

	-- The engine keeps mutable routing state (breakers, latency EMA) in module
	-- scope and a VM is reused across sessions; reset per session so a decision
	-- never depends on which pooled VM this session got.
	local session_config, lead = rotated_config(ctx.policy_seed)
	ctx.rotation_lead = lead
	ctx.tx_id = host_data.tx_id
	local ok, err = llm_policy.init(session_config)
	if not ok then
		error("llm_policy rejected the generated catalog: " .. tostring(err))
	end
	lib.log { level = "info", message = "llm rotation lead", provider = lead, tx_id = host_data.tx_id }
	lib.log {
		level = "info",
		message = "llm policy seed",
		seed = ctx.policy_seed,
		tx_id = host_data.tx_id,
		node_address = host_data.node_address,
	}

	local gen_per_time_unit_str = ctx.gas_data and ctx.gas_data.genPerTimeUnit
	local gen_per_time_unit = nil
	if gen_per_time_unit_str then
		local r = rat.new(gen_per_time_unit_str)
		if not r:is_zero() then
			gen_per_time_unit = r
		end
	end
	ctx.gen_per_time_unit = gen_per_time_unit

	local stop_on_spent = nil
	if gen_per_time_unit then
		stop_on_spent = gen_per_time_unit * rat.new(ctx.initial_time_units_allocation)
	end

	ctx.policy = {
		spent_gen_wei = rat.zero,
		exhausted = false,
		stop_on_spent = stop_on_spent,
	}
end

function Teardown(ctx)
	local data_dir = lib.rs.data_dir

	local has_stats = false
	for _ in pairs(ctx.stats) do
		has_stats = true
		break
	end
	if not has_stats then
		return
	end

	-- Stats persistence is best-effort telemetry: swallow failures so a transient
	-- SQLite issue (locked db, disk full, malformed file) does not break session
	-- teardown. `lib.finally` guarantees the db/stmt are released even on error.
	local ok, err = pcall(function()
		local db_path = data_dir .. "/stats.sqlite"
		local db = sqlite3.open(db_path)
		if not db then
			error("failed to open stats db at " .. db_path)
		end

		lib.finally(function()
			db:exec([[
				CREATE TABLE IF NOT EXISTS provider_stats (
					provider_model TEXT PRIMARY KEY,
					error_count INTEGER NOT NULL DEFAULT 0,
					input_tokens INTEGER NOT NULL DEFAULT 0,
					output_tokens INTEGER NOT NULL DEFAULT 0,
					total_tokens INTEGER NOT NULL DEFAULT 0,
					cache_read_tokens INTEGER NOT NULL DEFAULT 0,
					cache_write_tokens INTEGER NOT NULL DEFAULT 0,
					image_units INTEGER NOT NULL DEFAULT 0
				)
			]])

			local stmt = db:prepare([[
				INSERT INTO provider_stats (
					provider_model, error_count,
					input_tokens, output_tokens, total_tokens,
					cache_read_tokens, cache_write_tokens, image_units
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
				ON CONFLICT(provider_model) DO UPDATE SET
					error_count = error_count + excluded.error_count,
					input_tokens = input_tokens + excluded.input_tokens,
					output_tokens = output_tokens + excluded.output_tokens,
					total_tokens = total_tokens + excluded.total_tokens,
					cache_read_tokens = cache_read_tokens + excluded.cache_read_tokens,
					cache_write_tokens = cache_write_tokens + excluded.cache_write_tokens,
					image_units = image_units + excluded.image_units
			]])
			if not stmt then
				error("failed to prepare stats insert statement")
			end

			lib.finally(function()
				for key, entry in pairs(ctx.stats) do
					stmt:bind_values(
						key,
						entry.error_count,
						entry.input_tokens,
						entry.output_tokens,
						entry.total_tokens,
						entry.cache_read_tokens,
						entry.cache_write_tokens,
						entry.image_units
					)
					stmt:step()
					stmt:reset()
				end
			end, function()
				stmt:finalize()
			end)
		end, function()
			db:close()
		end)
	end)

	if not ok then
		lib.log {
			level = "warning",
			audience = "operator",
			message = "failed to persist llm stats during teardown",
			error = tostring(err),
		}
	end
end

function ExecPrompt(ctx, args, remaining_gen)
	---@cast args LLMExecPromptPayload
	---@cast remaining_gen number

	if ctx.policy.exhausted then
		llm.exhaust()
	end

	args.prompt = lib.rs.filter_text(args.prompt, {
		"NFKC",
		"RmZeroWidth",
		"NormalizeWS",
	})

	if args.prompt == "" then
		lib.rs.user_error {
			causes = { "EMPTY_PROMPT" },
			fatal = false,
			ctx = {},
		}
	end

	local mapped = llm.exec_prompt_transform(args)

	return dispatch_prompt(ctx, mapped, remaining_gen)
end

function ExecPromptTemplate(ctx, args, remaining_gen)
	---@cast args LLMExecPromptTemplatePayload
	---@cast remaining_gen number

	if ctx.policy.exhausted then
		return llm.exhaust()
	end

	local mapped = llm.exec_prompt_template_transform(args)

	return dispatch_prompt(ctx, mapped, remaining_gen)
end
