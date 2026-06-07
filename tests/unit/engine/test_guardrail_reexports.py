"""quality_guardrails / plot_state_machine 统一来源测试"""
from engine.application.quality_guardrails import (
    QualityGuardrail,
    LanguageStyleGuardrail,
    MacroPacingGuardrail,
)
from engine.runtime.quality_guardrails import (
    QualityGuardrail as RuntimeQualityGuardrail,
    LanguageStyleGuardrail as RuntimeLanguageStyleGuardrail,
    MacroPacingGuardrail as RuntimeMacroPacingGuardrail,
)
from engine.application.plot_state_machine import PlotStateMachine as AppPlotStateMachine
from engine.application.plot_state_machine.state_machine import PlotStateMachine as AppPlotStateMachineDirect
from engine.runtime.plot_state_machine import PlotStateMachine as RuntimePlotStateMachine


def test_application_quality_guardrails_are_runtime_classes():
    assert QualityGuardrail is RuntimeQualityGuardrail
    assert LanguageStyleGuardrail is RuntimeLanguageStyleGuardrail
    assert MacroPacingGuardrail is RuntimeMacroPacingGuardrail


def test_application_plot_state_machine_is_runtime_class():
    assert AppPlotStateMachine is RuntimePlotStateMachine
    assert AppPlotStateMachineDirect is RuntimePlotStateMachine
