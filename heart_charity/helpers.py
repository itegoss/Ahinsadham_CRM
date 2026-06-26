from .models import UserModuleAccess, UserRole

def get_user_permissions(user):
    """
    Returns permission object:
    can_add, can_update, can_delete
    (can_update maps to can_edit in your model)
    """

    # 0️⃣ Unauthenticated/Anonymous User → No permissions
    if not user or not user.is_authenticated:
        return {
            "can_add": False,
            "can_edit": False,
            "can_delete": False,
        }

    # 1️⃣ Superuser → Full Access
    if user.is_superuser:
        return {
            "can_add": True,
            "can_edit": True,   # superuser can do everything
            "can_delete": True,
        }

    # 2️⃣ Normal user → Check assigned role (UserRole → UserModuleAccess)
    try:
        user_role = UserRole.objects.get(user=user)
        role = user_role.role   # This is UserModuleAccess instance

        if role:
            return {
                "can_add": role.can_add,
                "can_edit": role.can_edit,   # IMPORTANT: your model uses can_edit
                "can_delete": role.can_delete,
            }

    except UserRole.DoesNotExist:
        pass

    # 3️⃣ Default → No permissions
    return {
        "can_add": False,
        "can_edit": False,
        "can_delete": False,
    }
