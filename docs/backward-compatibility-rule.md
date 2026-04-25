### Backwoard compatibility rule 


## Backward compatibility rule (mandatory for every change)

Before implementing any change, verify it won't break the **reference weak-machine config**: `qwen2.5:7b` + slim tools (8) + Ollama CPU. Run this config mentally or actually before marking a task done. No need to actually run the other LLMs but check against potential risks and do warn me.

**Checklist — answer all five before merging:**

1. **Default behavior preserved?** Does the change alter what happens when no env vars are set and provider is `ollama` with default model `qwen2.5:7b`?
2. **New setup step?** Does the change require something not already in `scripts/install.sh` (packages, browser installs, env vars)? If yes — add it to `install.sh` and document in Commands.
3. **Message history impact?** Does the change modify the structure or content of `messages[]` in a way the model might misinterpret (bootstrap additions, new system messages, rewritten tool entries)?
4. **Escape hatch present?** For any new default behaviour that changes model interaction, is there a `QA_NO_*` or `QA_DISABLE_*` env var to revert to the old behaviour?
5. **Tested on both configs?** Was it tested (or explicitly reasoned about) for both `qwen2.5:7b` slim and `llama3.1:8b` full?

**Reference configs to test/reason about:**

```bash
# Weak laptop (default Ollama, slim tools, CPU)
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=qwen2.5:7b \
  uv run python -m qa_agent.agent

# M4 Pro (full tools, GPU)
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=llama3.1:8b QA_FORCE_SLIM=false \
  uv run python -m qa_agent.agent

# Anthropic (CI / cloud)
uv run python -m qa_agent.agent   # default provider