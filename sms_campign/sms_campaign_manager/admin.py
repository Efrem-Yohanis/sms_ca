from django.contrib import admin

from .models import (
    AudienceMember,
    Campaign,
    Channel,
    CustomerProfileConfig,
    DatabaseConfig,
    DeliveryRecord,
    Language,
    MessageContent,
    Schedule,
    SentRecord,
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'sender_id', 'status',
        'is_ready_to_execute', 'created_at',
    )
    list_filter = ('status', 'is_ready_to_execute', 'is_deleted', 'created_at')
    search_fields = ('name', 'sender_id')
    readonly_fields = ('created_at', 'updated_at')
    @admin.register(SentRecord)
    class SentRecordAdmin(admin.ModelAdmin):
        list_display = ('id', 'campaign_id', 'batch_id', 'msisdn', 'sent_status', 'submitted_at', 'created_at')
        list_filter = ('sent_status', 'campaign_id', 'created_at')
        search_fields = ('msisdn', 'batch_id')
        readonly_fields = ('created_at', 'updated_at')
        ordering = ('-created_at',)
        date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    fieldsets = (
        ('Basic Information', {'fields': ('name', 'sender_id', 'channels')}),
        ('Status', {'fields': ('status', 'execution_status')}),
        ('Statistics', {'fields': (
            'total_messages', 'sent_count', 'delivered_count',
            'failed_count', 'pending_count',
        )}),
        ('Audit', {'fields': ('created_by', 'activated_by')}),
        ('Timestamps', {'fields': (
            'created_at', 'updated_at', 'activated_at',
            'execution_started_at', 'execution_paused_at',
            'execution_completed_at', 'stopped_at',
        )}),
        ('Soft Delete', {'fields': ('is_deleted', 'deleted_at', 'archived_at')}),
    )


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MessageContent)
class MessageContentAdmin(admin.ModelAdmin):
    list_display = ('id', 'campaign', 'default_language', 'languages_preview', 'updated_at')
    list_filter = ('default_language',)
    search_fields = ('campaign__name', 'campaign__sender_id')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Campaign', {'fields': ('campaign',)}),
        ('Language Content', {'fields': ('en', 'am', 'ti', 'om', 'so')}),
        ('Default Language', {'fields': ('default_language',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Languages with content')
    def languages_preview(self, obj):
        languages = obj.languages_with_content()
        return ', '.join(languages) if languages else '-'


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'campaign', 'schedule_type', 'start_date', 'end_date',
        'schedule_status', 'next_run_date',
    )
    list_filter = ('schedule_type', 'schedule_status', 'is_active')
    search_fields = ('campaign__name',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(DeliveryRecord)
class DeliveryRecordAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'campaign_id', 'batch_id', 'msisdn',
        'delivery_status', 'delivered_at', 'created_at',
    )
    list_filter = ('delivery_status', 'campaign_id', 'created_at')
    search_fields = ('msisdn', 'batch_id')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'


@admin.register(CustomerProfileConfig)
class CustomerProfileConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'database_config', 'table_name', 'default_language', 'is_active')
    list_filter = ('is_active', 'default_language')
    search_fields = ('name', 'table_name')


@admin.register(AudienceMember)
class AudienceMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'msisdn', 'language', 'language_source', 'is_valid', 'campaign_id')
    list_filter = ('language', 'language_source', 'is_valid')
    search_fields = ('msisdn',)
