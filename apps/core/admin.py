from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from .models import UsageLog, PCRSample

# Remove Groups - you don't need them
admin.site.unregister(Group)


# Custom User admin with better password management
class CustomUserAdmin(UserAdmin):
    list_display = (
    'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 'last_login')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)

    # Make password change more prominent
    fieldsets = UserAdmin.fieldsets + (
        ('Password Management', {
            'fields': (),
            'description': 'To change this user\'s password, use the "Change password" link in the top right of this form.'
        }),
    )


# Re-register User with custom admin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# Only register Usage Logs from your core models
@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = ('sample', 'user', 'checkout_date', 'return_date', 'volume_used', 'notes')
    list_filter = ('checkout_date', 'return_date', 'user')
    search_fields = ('sample__mikrogen_internal_number', 'user__username', 'notes')
    date_hierarchy = 'checkout_date'
    readonly_fields = ('checkout_date',)
    list_per_page = 50


# PCRSample admin for adding new columns and managing samples
@admin.register(PCRSample)
class PCRSampleAdmin(admin.ModelAdmin):
    list_display = (
        'mikrogen_internal_number',
        'provider_number',
        'provider',
        'target',
        'sample_type',
        'storage_place',
        'date_of_draw',
        'sample_volume',
        'sample_volume_remaining',
        'in_use',
        'current_user',
        'date_added'
    )
    list_filter = (
        'in_use',
        'not_found',
        'target',
        'sample_type',
        'provider',
        'storage_place',
        'gender',
        'extractor',
        'cycler'
    )
    search_fields = (
        'mikrogen_internal_number',
        'provider_number',
        'country_of_origin',
        'notes'
    )
    date_hierarchy = 'date_added'
    readonly_fields = ('date_added', 'last_modified')
    list_per_page = 50

    # Enable editing all fields
    fields = (
        'mikrogen_internal_number',
        'provider_number',
        'provider',
        'target',
        'sample_type',
        'storage_place',
        'date_of_draw',
        'age',
        'gender',
        'country_of_origin',
        'extraction_date',
        'extractor',
        'cycler',
        'mikrogen_pcr_kit',
        'external_pcr_kit',
        'mikrogen_ct_value',
        'external_ct_value',
        'sample_volume',
        'sample_volume_remaining',
        'notes',
        'in_use',
        'not_found',
        'current_user',
        'date_added',
        'last_modified'
    )

# Remove all the simple model registrations you don't need
# Don't register: Provider, Target, SampleType, StoragePlace, Extractor, Cycler, PCRKit
# These are managed through your Settings page instead