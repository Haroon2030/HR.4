import json as _json
from django import template

register = template.Library()


@register.filter
def from_json(value):
    """Parse a JSON string and return a dict; returns None on failure."""
    try:
        return _json.loads(value)
    except Exception:
        return None


@register.filter
def startswith(value, arg):
    """Check if value starts with arg"""
    if value and arg:
        return str(value).startswith(str(arg))
    return False

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary"""
    if dictionary and key:
        return dictionary.get(key)
    return None

@register.simple_tag
def active_class(request, pattern):
    """Return active class if URL matches pattern"""
    import re
    if re.search(pattern, request.path):
        return 'bg-primary-50 text-primary-700'
    return 'text-slate-600 hover:bg-slate-100'

@register.filter
def has_permission(user, permission_code):
    """
    Template filter للتحقق من صلاحية المستخدم
    
    الاستخدام:
        {% if request.user|has_permission:'employees.edit' %}
            <button>تعديل</button>
        {% endif %}
    """
    from apps.core.decorators import has_permission as check_permission
    return check_permission(user, permission_code)

@register.simple_tag(takes_context=True)
def user_has_permission(context, permission_code):
    """
    Template tag للتحقق من صلاحية المستخدم
    
    الاستخدام:
        {% user_has_permission 'employees.edit' as can_edit %}
        {% if can_edit %}
            <button>تعديل</button>
        {% endif %}
    """
    from apps.core.decorators import has_permission as check_permission
    user = context.get('request').user if 'request' in context else None
    if not user:
        return False
    return check_permission(user, permission_code)

@register.simple_tag(takes_context=True)
def user_permissions(context):
    """
    الحصول على كل صلاحيات المستخدم
    
    الاستخدام:
        {% user_permissions as perms %}
        {% if 'employees.edit' in perms %}
            <button>تعديل</button>
        {% endif %}
    """
    from apps.core.decorators import get_user_permissions
    user = context.get('request').user if 'request' in context else None
    if not user:
        return []
    return get_user_permissions(user)
