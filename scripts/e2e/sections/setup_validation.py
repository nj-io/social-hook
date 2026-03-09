"""Section I: Setup Validation scenarios."""


def run(harness, runner):
    """I1-I3: Setup validation scenarios."""
    config = harness.load_config()

    # I1: Valid Anthropic key
    def i1():
        from social_hook.setup.validation import validate_anthropic_key

        key = config.env.get("ANTHROPIC_API_KEY", "")
        if not key:
            return "SKIP: No ANTHROPIC_API_KEY (provider not configured)"
        ok, msg = validate_anthropic_key(key)
        assert ok, f"Validation failed: {msg}"
        return msg

    runner.run_scenario("I1", "Valid Anthropic key", i1)

    # I2: Valid Telegram token
    def i2():
        from social_hook.setup.validation import validate_telegram_bot

        token = config.env.get("TELEGRAM_BOT_TOKEN", "")
        assert token, "No TELEGRAM_BOT_TOKEN in config"
        ok, msg = validate_telegram_bot(token)
        assert ok, f"Validation failed: {msg}"
        return msg

    runner.run_scenario("I2", "Valid Telegram token", i2)

    # I3: Invalid Anthropic key
    def i3():
        from social_hook.setup.validation import validate_anthropic_key

        ok, msg = validate_anthropic_key("sk-ant-bad-key-12345")
        assert not ok, f"Expected validation failure, got success: {msg}"
        return f"Correctly rejected: {msg[:60]}"

    runner.run_scenario("I3", "Invalid Anthropic key", i3)
