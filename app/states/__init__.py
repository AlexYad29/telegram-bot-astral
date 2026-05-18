"""FSM-состояния. Хранятся отдельно от хендлеров, чтобы их можно было
переиспользовать (например, из админских команд) без циклических импортов.
"""

from app.states.compatibility import CompatibilityStates
from app.states.profile import ProfileRegistrationStates

__all__ = ["CompatibilityStates", "ProfileRegistrationStates"]
