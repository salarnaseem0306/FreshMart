from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class FreshMartUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("FreshMart", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("FreshMart", {"fields": ("role",)}),)