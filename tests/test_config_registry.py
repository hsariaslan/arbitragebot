import unittest

from config_registry import Config, ConfigGroup, ConfigRegistry


class ConfigRegistryTests(unittest.TestCase):
    def test_multi_config_allows_super_primary_demo(self) -> None:
        group = ConfigGroup(
            id="group",
            name="Group",
            initial_capital=1000.0,
            order=0,
            configs=[
                Config(
                    id="cfg-a",
                    group_id="group",
                    name="A",
                    description="",
                    is_primary=True,
                    is_default=True,
                    order=0,
                    settings={},
                ),
                Config(
                    id="cfg-b",
                    group_id="group",
                    name="B",
                    description="",
                    is_primary=False,
                    is_default=False,
                    order=1,
                    settings={},
                ),
            ],
        )
        registry = ConfigRegistry(
            shared={
                "execution_mode": "demo",
                "hedge_execution_mode": "simulation",
                "super_primary_config_id": "cfg-a",
            },
            groups=[group],
        )

        self.assertEqual(registry.effective_execution_mode("cfg-a"), "demo")
        self.assertEqual(registry.effective_execution_mode("cfg-b"), "simulation")


if __name__ == "__main__":
    unittest.main()
