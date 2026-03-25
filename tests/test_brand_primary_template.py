"""Tests for the brand-primary strategy template and get_template_defaults()."""

from social_hook.setup.templates import (
    STRATEGY_TEMPLATES,
    get_template,
    get_template_defaults,
    templates_to_dicts,
)


class TestBrandPrimaryTemplate:
    """Tests for the brand-primary template in STRATEGY_TEMPLATES."""

    def test_brand_primary_exists_in_templates(self):
        """Brand-primary template is present in the templates list."""
        ids = [t.id for t in STRATEGY_TEMPLATES]
        assert "brand-primary" in ids

    def test_get_template_returns_brand_primary(self):
        """get_template('brand-primary') returns the correct template."""
        t = get_template("brand-primary")
        assert t is not None
        assert t.id == "brand-primary"
        assert t.name == "Brand & Marketing"

    def test_brand_primary_defaults(self):
        """Brand-primary template has correct default values."""
        t = get_template("brand-primary")
        assert t is not None
        d = t.defaults
        assert d.identity == "company"
        assert d.technical_level == "intermediate"
        assert d.platform_filter == "significant"
        assert d.platform_frequency == "low"
        assert "scroll-stop" in d.voice_tone
        assert "value prop" in d.post_when
        assert "visual proof" in d.avoid
        assert "[company]" in d.example_intro_hook

    def test_brand_primary_description(self):
        """Brand-primary template has a meaningful description."""
        t = get_template("brand-primary")
        assert t is not None
        assert "marketing" in t.description.lower()


class TestGetTemplateDefaults:
    """Tests for get_template_defaults()."""

    def test_returns_dict_for_brand_primary(self):
        """get_template_defaults('brand-primary') returns a field dict."""
        defaults = get_template_defaults("brand-primary")
        assert defaults is not None
        assert isinstance(defaults, dict)
        expected_keys = {
            "identity",
            "voice_tone",
            "audience",
            "technical_level",
            "platform_filter",
            "platform_frequency",
            "post_when",
            "avoid",
            "example_intro_hook",
        }
        assert set(defaults.keys()) == expected_keys

    def test_returns_dict_for_existing_template(self):
        """get_template_defaults works for other existing templates too."""
        defaults = get_template_defaults("building-public")
        assert defaults is not None
        assert defaults["identity"] == "myself"

    def test_returns_none_for_unknown(self):
        """get_template_defaults('unknown') returns None."""
        assert get_template_defaults("unknown") is None

    def test_returns_none_for_empty_string(self):
        """get_template_defaults('') returns None."""
        assert get_template_defaults("") is None

    def test_defaults_match_template(self):
        """Returned dict values match the template's StrategyDefaults fields."""
        t = get_template("brand-primary")
        defaults = get_template_defaults("brand-primary")
        assert defaults is not None
        assert t is not None
        assert defaults["identity"] == t.defaults.identity
        assert defaults["voice_tone"] == t.defaults.voice_tone
        assert defaults["audience"] == t.defaults.audience
        assert defaults["technical_level"] == t.defaults.technical_level
        assert defaults["platform_filter"] == t.defaults.platform_filter
        assert defaults["platform_frequency"] == t.defaults.platform_frequency
        assert defaults["post_when"] == t.defaults.post_when
        assert defaults["avoid"] == t.defaults.avoid
        assert defaults["example_intro_hook"] == t.defaults.example_intro_hook


class TestTemplatesToDictsIncludesBrandPrimary:
    """Tests that templates_to_dicts() includes brand-primary."""

    def test_brand_primary_in_serialized_output(self):
        """templates_to_dicts() includes brand-primary in API serialization."""
        dicts = templates_to_dicts()
        ids = [d["id"] for d in dicts]
        assert "brand-primary" in ids

    def test_brand_primary_serialized_defaults(self):
        """Brand-primary defaults are correctly serialized with camelCase keys."""
        dicts = templates_to_dicts()
        bp = next(d for d in dicts if d["id"] == "brand-primary")
        defaults = bp["defaults"]
        assert defaults["identity"] == "company"
        assert "voiceTone" in defaults
        assert "technicalLevel" in defaults
        assert "platformFilter" in defaults
        assert "platformFrequency" in defaults
        assert "postWhen" in defaults
        assert "exampleIntroHook" in defaults
