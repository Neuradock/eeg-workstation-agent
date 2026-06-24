import unittest

from neuradock_agent.agent import route_intent
from neuradock_agent.llm import _parse_plan_response


class AgentRouterTests(unittest.TestCase):
    def test_routes_supported_intents(self):
        self.assertEqual(route_intent("check signal quality"), "signal_quality")
        self.assertEqual(route_intent("find weak alpha waves"), "alpha_dynamics")
        self.assertEqual(route_intent("画功率谱和频带功率"), "psd_bandpower")
        self.assertEqual(
            route_intent("离线计算视觉认知负荷"),
            "visual_cognitive_load",
        )
        self.assertEqual(route_intent("连接设备做实时检查"), "device_doctor")
        self.assertEqual(route_intent("try the demo"), "demo")
        self.assertEqual(
            route_intent("compare rest and task visual cognitive load"),
            "visual_cognitive_load_comparison",
        )

    def test_rejects_unknown_request(self):
        self.assertEqual(route_intent("diagnose depression"), "unsupported")

    def test_llm_plan_is_constrained_to_allowlist(self):
        plan = _parse_plan_response(
            '{"intent":"psd_bandpower","reason":"spectral request"}', "test-model"
        )
        self.assertEqual(plan.intent, "psd_bandpower")
        rejected = _parse_plan_response(
            '{"intent":"execute_python","reason":"unsafe"}', "test-model"
        )
        self.assertEqual(rejected.intent, "unsupported")
        offline = _parse_plan_response(
            '{"intent":"visual_cognitive_load","reason":"offline alpha features"}',
            "test-model",
        )
        self.assertEqual(offline.intent, "visual_cognitive_load")
        alpha = _parse_plan_response(
            '{"intent":"alpha_dynamics","reason":"strong weak alpha"}',
            "test-model",
        )
        self.assertEqual(alpha.intent, "alpha_dynamics")
        comparison = _parse_plan_response(
            (
                '{"intent":"visual_cognitive_load_comparison",'
                '"reason":"compare two conditions"}'
            ),
            "test-model",
        )
        self.assertEqual(
            comparison.intent,
            "visual_cognitive_load_comparison",
        )


if __name__ == "__main__":
    unittest.main()
