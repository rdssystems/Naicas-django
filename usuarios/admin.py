from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'perfil no Naicas'


admin.site.unregister(User)


@admin.register(User)
class NaicasUserAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ('username', 'first_name', 'last_name', 'nivel', 'escola', 'is_active')
    list_select_related = ('profile', 'profile__escola')

    @admin.display(description='nível')
    def nivel(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.get_nivel_acesso_display() if profile else '—'

    @admin.display(description='unidade')
    def escola(self, obj):
        profile = getattr(obj, 'profile', None)
        return profile.escola if profile and profile.escola else '—'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'nivel_acesso', 'escola')
    list_filter = ('nivel_acesso', 'escola')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
