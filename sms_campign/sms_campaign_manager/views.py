"""API views for Campaign Manager."""

import logging
import os
import requests
import uuid
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage, get_connection
from django.db.models import Case, CharField, Count, Exists, F, IntegerField, Max, Min, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.generics import CreateAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView, UpdateAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view

from .constants import SUPPORTED_LANGUAGES
from .models import (
	AudienceConfig,
	AudienceBuildJob,
	Audience,
	AudienceMember,
	Campaign,
	Channel,
	CustomerProfileConfig,
	DatabaseConfig,
	DeliveryRecord,
	EmailConfig,
	EmailReport,
	FailedDelivery,
	FailedSent,
	GlobalTPSConfig,
	NAddressesConfig,
	ReportSubscription,
	ReportDeliveryLog,
	CampaignProgressReport,
	Language,
	MessageContent,
	MessageObject,
	MessageBuildJob,
	Schedule,
	SentRecord,
	SuccessDelivery,
	SuccessSent,
	SenderID,
	SMSCConfig,
)
from .pagination import StandardPagination
from .platform_accounts import clear_password_change_requirement, get_platform_profile
from .serializers import (
	CampaignCreateUpdateSerializer,
	CampaignDetailSerializer,
	CampaignListSerializer,
	ChannelSerializer,
	CampaignReadinessSerializer,
	AudienceConfigSerializer,
	CustomerProfileConfigSerializer,
	CustomerProfilePreviewSerializer,
	AudienceMemberSerializer,
	ManualAudienceInputSerializer,
	ManualAudienceSerializer,
	FileAudienceSerializer,
	DatabaseAudienceSerializer,
	SentRecordBulkCreateSerializer,
	SentRecordBulkUpdateSerializer,
	SentRecordCreateSerializer,
	SentRecordSerializer,
	SentRecordUpdateSerializer,
	DatabaseConfigCreateUpdateSerializer,
	DatabaseConfigSerializer,
	DatabaseConfigTestParamsSerializer,
	DatabaseConfigTestResponseSerializer,
	DeliveryRecordBulkCreateSerializer,
	DeliveryRecordBulkUpdateSerializer,
	DeliveryRecordCreateSerializer,
	DeliveryRecordSerializer,
	DeliveryRecordUpdateSerializer,
	EmailConfigSerializer,
	EmailConfigCreateUpdateSerializer,
	GlobalTPSConfigSerializer,
	NAddressesConfigSerializer,
	EmailConfigTestParamsSerializer,
	EmailReportSerializer,
	CampaignEmailReportCreateSerializer,
	ReportSubscriptionSerializer,
	ReportDeliveryLogSerializer,
	CampaignProgressReportSerializer,
	 UserRegistrationSerializer,
	 CampaignTokenObtainPairSerializer,
	UserSerializer,
	UserAdminUpdateSerializer,
	PasswordChangeSerializer,
	LanguageSerializer,
	MessageContentCreateUpdateSerializer,
	MessageContentSerializer,
	MessageContentApiInputSerializer,
	MessageContentApiSerializer,
	SupportedLanguageSerializer,
	ScheduleCreateUpdateSerializer,
	ScheduleSerializer,
	SenderIDSerializer,
	SenderIDCreateUpdateSerializer,
	SMSCConfigSerializer,
	SMSCConfigCreateUpdateSerializer,
)
from .services.database_connector import DatabaseConnector
from .services.language_mapper import LanguageMapper
from .services.delivery_tracker_service import DeliveryTrackerService
from .services.campaign_actions import CampaignActionsService
from .services.campaign_readiness import CampaignReadinessService
from .services.audience_service import AudienceService, AudienceBuildService
from .services.sent_tracker_service import SentTrackerService
from .services.message_builder import MessageBuilder
from .services.campaign_progress_reports import build_campaigns_report_content
from .services.email_reports import (
	next_subscription_run_at,
	send_campaign_report,
	send_subscription_report,
)

logger = logging.getLogger(__name__)


class CampaignLoginView(TokenObtainPairView):
	serializer_class = CampaignTokenObtainPairSerializer


class CampaignInitialPasswordChangeView(APIView):
	permission_classes = [AllowAny]
	authentication_classes = []

	def post(self, request):
		identifier = request.data.get('username', '')
		current_password = request.data.get('current_password', '')
		new_password = request.data.get('new_password', '')
		if not all(isinstance(value, str) and value for value in (identifier, current_password, new_password)):
			return Response({'detail': 'Username, current password, and new password are required.'}, status=status.HTTP_400_BAD_REQUEST)
		User = get_user_model()
		user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
		platform_profile = get_platform_profile(user.pk) if user else None
		if not (
			user and user.is_active and user.check_password(current_password)
			and platform_profile
			and platform_profile[0] == 'CAMPAIGN_MANAGER'
			and platform_profile[1]
		):
			return Response({'detail': 'The temporary sign-in could not be verified.'}, status=status.HTTP_400_BAD_REQUEST)
		try:
			validate_password(new_password, user=user)
		except DjangoValidationError as error:
			return Response({'new_password': error.messages}, status=status.HTTP_400_BAD_REQUEST)
		with transaction.atomic():
			if not clear_password_change_requirement(user.pk):
				return Response({'detail': 'The temporary password has already been changed.'}, status=status.HTTP_409_CONFLICT)
			user.set_password(new_password)
			user.save(update_fields=['password'])
		return Response({'success': True})


def _audience_counts(campaign):
	if hasattr(campaign, 'audience_total'):
		return {
			'total': campaign.audience_total,
			'valid': campaign.audience_valid,
			'invalid': campaign.audience_invalid,
		}
	return AudienceMember.objects.filter(campaign=campaign).aggregate(
		total=Count('id'),
		valid=Count('id', filter=Q(is_valid=True)),
		invalid=Count('id', filter=Q(is_valid=False)),
	)


def _audience_campaign_payload(campaign):
	config = getattr(campaign, 'audience_config', None)
	counts = _audience_counts(campaign)
	total = counts['total'] or 0
	valid = counts['valid'] or 0
	invalid = counts['invalid'] or 0
	percentage = valid * 100 / total if total else 0
	created_at = config.created_at if config else campaign.created_at
	updated_at = config.updated_at if config else campaign.updated_at
	preview = [
		{'msisdn': member.msisdn, 'lang': member.language.code}
		for member in AudienceMember.objects.filter(campaign=campaign)
		.select_related('language').order_by('sequence_number')[:20]
	]
	payload = {
		'id': campaign.id,
		'campaign': campaign.id,
		'campaign_info': {
			'id': campaign.id,
			'name': campaign.name,
			'status': campaign.status,
			'execution_status': campaign.status,
		},
		'total_count': total,
		'valid_count': valid,
		'invalid_count': invalid,
		'valid_percentage': percentage,
		'summary': {'total': total, 'valid': valid, 'invalid': invalid},
		'database_table': config.source_table if config else '',
		'id_field': config.source_msisdn_column if config else '',
		'filter_condition': config.source_filter_clause if config else '',
		'created_at': created_at,
		'updated_at': updated_at,
		'recipients_preview': preview,
	}
	if config:
		latest_job = config.build_jobs.order_by('-created_at').first()
		payload['audience_config'] = {
			'id': config.id,
			'source_type': config.source_type,
			'source_database_id': config.source_database_id,
			'source_database_name': config.source_database.name if config.source_database_id else '',
			'source_table': config.source_table,
			'source_msisdn_column': config.source_msisdn_column,
			'source_language_column': config.source_language_column,
			'source_filter_clause': config.source_filter_clause,
			'mapper_enabled': config.mapper_enabled,
			'mapper_database_id': config.mapper_database_id,
			'mapper_database_name': config.mapper_database.name if config.mapper_database_id else '',
			'mapper_table': config.mapper_table,
			'mapper_msisdn_column': config.mapper_msisdn_column,
			'mapper_language_column': config.mapper_language_column,
			'default_language': config.default_language.code if config.default_language_id else '',
			'rebuild_before_each_run': config.rebuild_before_each_run,
			'rebuild_on_each_round': config.rebuild_on_each_round,
			'rebuild_minutes_before': config.rebuild_minutes_before,
			'rebuild_timeout_minutes': config.rebuild_timeout_minutes,
			'total_count': config.total_count,
			'valid_count': config.valid_count,
			'invalid_count': config.invalid_count,
			'language_from_source': config.language_from_source,
			'language_from_mapper': config.language_from_mapper,
			'language_from_default': config.language_from_default,
			'is_processed': config.is_processed,
			'last_built_at': config.last_built_at,
			'created_at': config.created_at,
			'updated_at': config.updated_at,
		}
		payload['build_job'] = {
			'id': latest_job.id,
			'status': latest_job.status,
			'processed_rows': latest_job.processed_rows,
			'valid_rows': latest_job.valid_rows,
			'invalid_rows': latest_job.invalid_rows,
			'error_message': latest_job.error_message,
			'created_at': latest_job.created_at,
		} if latest_job else None
		if config.source_type == 'database':
			payload['database_info'] = {
				'table': config.source_table,
				'id_field': config.source_msisdn_column,
				'filter': config.source_filter_clause,
			}
	return payload


class AudienceCollectionView(APIView):
	@extend_schema(tags=['Audience Management'], summary='List campaign audiences')
	def get(self, request):
		members = AudienceMember.objects.filter(campaign_id=OuterRef('pk'))
		configs = AudienceConfig.objects.filter(campaign_id=OuterRef('pk'))
		campaigns = Campaign.objects.filter(is_deleted=False).annotate(
			has_audience_members=Exists(members),
			has_audience_config=Exists(configs),
		).filter(
			Q(has_audience_members=True) | Q(has_audience_config=True)
		).select_related(
			'audience_config', 'audience_config__source_database',
			'audience_config__mapper_database', 'audience_config__default_language',
		).order_by('-created_at')
		campaign_filter = request.query_params.get('campaign')
		if campaign_filter:
			campaigns = campaigns.filter(id=campaign_filter)
		paginator = StandardPagination()
		page = paginator.paginate_queryset(campaigns, request)
		return paginator.get_paginated_response([
			_audience_campaign_payload(campaign) for campaign in page
		])


class AudienceSummaryView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Summarize campaign audiences')
	def get(self, request):
		campaigns = Campaign.objects.filter(is_deleted=False).filter(
			Q(audience_members__isnull=False) | Q(audience_config__isnull=False)
		).distinct()
		counts = AudienceMember.objects.filter(campaign__is_deleted=False).aggregate(
			total=Count('id'),
			valid=Count('id', filter=Q(is_valid=True)),
			invalid=Count('id', filter=Q(is_valid=False)),
		)
		total = counts['total'] or 0
		valid = counts['valid'] or 0
		by_status = {
			row['status']: row['count']
			for row in campaigns.values('status').annotate(count=Count('id', distinct=True)).order_by()
		}
		return Response({
			'total_audiences': campaigns.count(),
			'total_recipients': total,
			'total_valid': valid,
			'total_invalid': counts['invalid'] or 0,
			'avg_valid_percentage': valid * 100 / total if total else 0,
			'by_campaign_status': by_status,
		})


class AudienceResourceView(APIView):
	def _campaign(self, pk):
		campaign = get_object_or_404(Campaign, id=pk, is_deleted=False)
		if not AudienceMember.objects.filter(campaign=campaign).exists() and not AudienceConfig.objects.filter(campaign=campaign).exists():
			from django.http import Http404
			raise Http404
		return campaign

	@extend_schema(tags=['Audience Management'], summary='Get campaign audience details')
	def get(self, request, pk):
		return Response(_audience_campaign_payload(self._campaign(pk)))

	def _replace_members(self, request, pk):
		campaign = self._campaign(pk)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		recipients = request.data.get('recipients')
		if not isinstance(recipients, list):
			return Response({'recipients': ['Expected a list of recipients.']}, status=status.HTTP_400_BAD_REQUEST)
		config = AudienceConfig.objects.filter(campaign=campaign).select_related('default_language').first()
		default_language = config.default_language.code if config else 'en'
		serializer = ManualAudienceInputSerializer(data={
			'msisdns': [item.get('msisdn', '') for item in recipients if isinstance(item, dict)],
			'languages': [item.get('lang', '') for item in recipients if isinstance(item, dict)],
			'default_language': default_language,
		})
		serializer.is_valid(raise_exception=True)
		AudienceService(campaign, default_language).create_from_manual(
			serializer.validated_data['msisdns'],
			serializer.validated_data.get('languages'),
			'manual',
		)
		return Response(_audience_campaign_payload(campaign))

	@extend_schema(tags=['Audience Management'], summary='Replace campaign audience recipients')
	def put(self, request, pk):
		return self._replace_members(request, pk)

	@extend_schema(tags=['Audience Management'], summary='Update campaign audience recipients')
	def patch(self, request, pk):
		return self._replace_members(request, pk)

	@extend_schema(tags=['Audience Management'], summary='Delete campaign audience')
	def delete(self, request, pk):
		campaign = self._campaign(pk)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		with transaction.atomic():
			AudienceMember.objects.filter(campaign=campaign).delete()
			AudienceConfig.objects.filter(campaign=campaign).delete()
		campaign.refresh_readiness_flag()
		return Response(status=status.HTTP_204_NO_CONTENT)


class AudienceStatisticsView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get campaign audience statistics')
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, id=pk, is_deleted=False)
		members = AudienceMember.objects.filter(campaign=campaign)
		counts = members.aggregate(
			total=Count('id'),
			valid=Count('id', filter=Q(is_valid=True)),
			invalid=Count('id', filter=Q(is_valid=False)),
		)
		total = counts['total'] or 0
		valid = counts['valid'] or 0
		languages = {
			row['language__code']: row['count']
			for row in members.filter(is_valid=True).values('language__code').annotate(count=Count('id'))
		}
		invalid_samples = [
			{'msisdn': member.msisdn, 'lang': member.language.code, 'error': member.validation_error}
			for member in members.filter(is_valid=False).select_related('language').order_by('sequence_number')[:10]
		]
		return Response({
			'audience_id': campaign.id,
			'campaign_id': campaign.id,
			'campaign_name': campaign.name,
			'total_count': total,
			'valid_count': valid,
			'invalid_count': counts['invalid'] or 0,
			'valid_percentage': valid * 100 / total if total else 0,
			'invalid_percentage': (counts['invalid'] or 0) * 100 / total if total else 0,
			'language_distribution': languages,
			'invalid_samples': invalid_samples,
		})


class AudienceRecipientsPreviewView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Preview campaign audience recipients')
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, id=pk, is_deleted=False)
		members = AudienceMember.objects.filter(campaign=campaign).select_related('language').order_by('sequence_number')
		total = members.count()
		preview = [
			{'msisdn': member.msisdn, 'lang': member.language.code}
			for member in members[:100]
		]
		return Response({
			'audience_id': campaign.id,
			'campaign_id': campaign.id,
			'campaign_name': campaign.name,
			'total_recipients': total,
			'valid_recipients': members.filter(is_valid=True).count(),
			'invalid_recipients': members.filter(is_valid=False).count(),
			'preview': preview,
			'preview_count': len(preview),
			'has_more': total > len(preview),
		})


def annotate_campaign_child_ids(queryset):
    return queryset.annotate(
        audience_id=Subquery(
			AudienceConfig.objects.filter(campaign_id=OuterRef('pk')).values('id')[:1],
        ),
        message_content_id=Subquery(
            MessageContent.objects.filter(campaign_id=OuterRef('pk')).values('id')[:1],
        ),
        schedule_id=Subquery(
            Schedule.objects.filter(campaign_id=OuterRef('pk')).values('id')[:1],
        ),
    )


def _campaign_record_count(model, **filters):
	queryset = (
		model.objects
		.filter(campaign_id=OuterRef('pk'), **filters)
		.order_by()
		.values('campaign_id')
		.annotate(total=Count('pk'))
		.values('total')[:1]
	)
	return Coalesce(
		Subquery(queryset, output_field=IntegerField()),
		Value(0),
		output_field=IntegerField(),
	)


class UserRegistrationView(CreateAPIView):
	serializer_class = UserRegistrationSerializer
	permission_classes = [AllowAny]


class CurrentUserView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(tags=['User Management'], summary='Get current user', responses={200: UserSerializer})
	def get(self, request):
		return Response(UserSerializer(request.user).data)

	@extend_schema(tags=['User Management'], summary='Update current user profile', request=UserSerializer, responses={200: UserSerializer})
	def patch(self, request):
		serializer = UserSerializer(request.user, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class PasswordChangeView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(tags=['User Management'], summary='Change current user password', request=PasswordChangeSerializer, responses={200: OpenApiResponse(description='Password changed.')})
	def post(self, request):
		serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		if not request.user.check_password(serializer.validated_data['old_password']):
			return Response({'old_password': ['Current password is incorrect.']}, status=status.HTTP_400_BAD_REQUEST)
		request.user.set_password(serializer.validated_data['new_password'])
		request.user.save(update_fields=['password'])
		return Response({'success': True, 'message': 'Password changed successfully.'})


class UserAdminListCreateView(ListCreateAPIView):
	queryset = get_user_model().objects.all().order_by('username')
	permission_classes = [IsAdminUser]
	serializer_class = UserSerializer

	@extend_schema(tags=['User Management'], summary='List users', responses={200: UserSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['User Management'], summary='Create user', request=UserRegistrationSerializer, responses={201: UserSerializer})
	def post(self, request, *args, **kwargs):
		serializer = UserRegistrationSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		return Response(UserSerializer(serializer.save()).data, status=status.HTTP_201_CREATED)


class UserAdminDetailView(RetrieveUpdateDestroyAPIView):
	queryset = get_user_model().objects.all()
	permission_classes = [IsAdminUser]
	serializer_class = UserAdminUpdateSerializer

	@extend_schema(tags=['User Management'], summary='Get user', responses={200: UserSerializer})
	def get(self, request, *args, **kwargs):
		return Response(UserSerializer(self.get_object()).data)

	@extend_schema(tags=['User Management'], summary='Update user', request=UserAdminUpdateSerializer, responses={200: UserSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['User Management'], summary='Patch user', request=UserAdminUpdateSerializer, responses={200: UserSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['User Management'], summary='Delete user', responses={204: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class SenderIDListCreateView(ListCreateAPIView):
	queryset = SenderID.objects.all()
	serializer_class = SenderIDSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		active = self.request.query_params.get('is_active')
		if active is not None and active.lower() in {'true', 'false'}:
			queryset = queryset.filter(is_active=(active.lower() == 'true'))
		return queryset

	@extend_schema(tags=['Sender IDs'], summary='List sender IDs', responses={200: SenderIDSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Sender IDs'], summary='Create sender ID', request=SenderIDCreateUpdateSerializer, responses={201: SenderIDSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)


class SenderIDDetailView(RetrieveUpdateDestroyAPIView):
	queryset = SenderID.objects.all()
	serializer_class = SenderIDSerializer

	@extend_schema(tags=['Sender IDs'], summary='Get sender ID', responses={200: SenderIDSerializer})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Sender IDs'], summary='Update sender ID', request=SenderIDCreateUpdateSerializer, responses={200: SenderIDSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['Sender IDs'], summary='Patch sender ID', request=SenderIDCreateUpdateSerializer, responses={200: SenderIDSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['Sender IDs'], summary='Delete sender ID', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class GlobalTPSConfigListCreateView(ListCreateAPIView):
	queryset = GlobalTPSConfig.objects.all()
	serializer_class = GlobalTPSConfigSerializer

	def perform_create(self, serializer):
		user = self.request.user
		serializer.save(created_by=user if user.is_authenticated else None)

	@extend_schema(tags=['Global TPS Config'], summary='List global TPS configurations', responses={200: GlobalTPSConfigSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Global TPS Config'], summary='Create global TPS configuration', request=GlobalTPSConfigSerializer, responses={201: GlobalTPSConfigSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)


class GlobalTPSConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = GlobalTPSConfig.objects.all()
	serializer_class = GlobalTPSConfigSerializer


class GlobalTPSConfigActiveView(APIView):
	@extend_schema(tags=['Global TPS Config'], summary='Get active global TPS configuration')
	def get(self, request):
		config = GlobalTPSConfig.get_active()
		if config is None:
			return Response({'success': False, 'detail': 'No active global TPS config.'}, status=status.HTTP_404_NOT_FOUND)
		return Response({'success': True, 'data': {
			'id': config.id,
			'name': config.name,
			'global_tps': config.global_tps,
			'updated_at': config.updated_at,
		}})


class NAddressesConfigListCreateView(ListCreateAPIView):
	queryset = NAddressesConfig.objects.all()
	serializer_class = NAddressesConfigSerializer

	def perform_create(self, serializer):
		user = self.request.user
		serializer.save(created_by=user if user.is_authenticated else None)

	@extend_schema(tags=['N-Addresses Config'], summary='List N-addresses configurations', responses={200: NAddressesConfigSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['N-Addresses Config'], summary='Create N-addresses configuration', request=NAddressesConfigSerializer, responses={201: NAddressesConfigSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)


class NAddressesConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = NAddressesConfig.objects.all()
	serializer_class = NAddressesConfigSerializer


class NAddressesConfigActiveView(APIView):
	@extend_schema(tags=['N-Addresses Config'], summary='Get active N-addresses configuration')
	def get(self, request):
		config = NAddressesConfig.get_active()
		if config is None:
			return Response({'success': False, 'detail': 'No active N-addresses config.'}, status=status.HTTP_404_NOT_FOUND)
		return Response({'success': True, 'data': {
			'id': config.id,
			'name': config.name,
			'max_addresses_per_request': config.max_addresses_per_request,
			'updated_at': config.updated_at,
		}})


class SMSCConfigListCreateView(ListCreateAPIView):
	queryset = SMSCConfig.objects.all()
	serializer_class = SMSCConfigSerializer

	@extend_schema(tags=['SMSC Config'], summary='List SMSC configurations', responses={200: SMSCConfigSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['SMSC Config'], summary='Create SMSC configuration', request=SMSCConfigCreateUpdateSerializer, responses={201: SMSCConfigSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)


class SMSCConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = SMSCConfig.objects.all()
	serializer_class = SMSCConfigSerializer

	@extend_schema(tags=['SMSC Config'], summary='Get SMSC configuration', responses={200: SMSCConfigSerializer})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['SMSC Config'], summary='Update SMSC configuration', request=SMSCConfigCreateUpdateSerializer, responses={200: SMSCConfigSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['SMSC Config'], summary='Patch SMSC configuration', request=SMSCConfigCreateUpdateSerializer, responses={200: SMSCConfigSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['SMSC Config'], summary='Delete SMSC configuration', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class EmailConfigListCreateView(ListCreateAPIView):
	queryset = EmailConfig.objects.all()
	serializer_class = EmailConfigSerializer

	@extend_schema(tags=['Email Config'], summary='List email configurations', responses={200: EmailConfigSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Email Config'], summary='Create email configuration', request=EmailConfigCreateUpdateSerializer, responses={201: EmailConfigSerializer})
	def post(self, request, *args, **kwargs):
		serializer = EmailConfigCreateUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = getattr(request, 'user', None)
		if getattr(user, 'is_authenticated', False):
			serializer.validated_data['created_by'] = user
		instance = serializer.save()
		return Response(EmailConfigSerializer(instance).data, status=status.HTTP_201_CREATED)


class EmailConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = EmailConfig.objects.all()
	serializer_class = EmailConfigSerializer

	@extend_schema(tags=['Email Config'], summary='Get email configuration', responses={200: EmailConfigSerializer})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Email Config'], summary='Update email configuration', request=EmailConfigCreateUpdateSerializer, responses={200: EmailConfigSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['Email Config'], summary='Patch email configuration', request=EmailConfigCreateUpdateSerializer, responses={200: EmailConfigSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['Email Config'], summary='Delete email configuration', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class EmailConfigTestView(APIView):
	@extend_schema(tags=['Email Config'], summary='Test SMTP settings and optionally send a test email', request=EmailConfigTestParamsSerializer, responses={200: OpenApiResponse(description='SMTP test result.')})
	def post(self, request, pk=None):
		config = None
		if pk is not None:
			config = get_object_or_404(EmailConfig, pk=pk)
			payload = {
				'host': config.host,
				'port': config.port,
				'username': config.username,
				'password': config.password,
				'use_tls': config.use_tls,
				'use_ssl': config.use_ssl,
				'default_from_email': config.default_from_email,
			}
			test_email = request.data.get('test_email', '')
		else:
			serializer = EmailConfigTestParamsSerializer(data=request.data)
			serializer.is_valid(raise_exception=True)
			payload = serializer.validated_data
			test_email = payload.pop('test_email', '')

		try:
			connection = get_connection(
				host=payload['host'],
				port=payload['port'],
				username=payload.get('username', ''),
				password=payload.get('password', ''),
				use_tls=payload.get('use_tls', False),
				use_ssl=payload.get('use_ssl', False),
				fail_silently=False,
			)
			if test_email:
				EmailMessage(
					subject='SMTP configuration test',
					body='This is a test email from the SMS Campaign Manager.',
					from_email=payload.get('default_from_email') or None,
					to=[test_email],
					connection=connection,
				).send(fail_silently=False)
				message = f'Test email sent to {test_email}.'
			else:
				connection.open()
				connection.close()
				message = 'SMTP connection successful.'
			if config:
				config.last_tested_at = timezone.now()
				config.last_test_status = 'success'
				config.last_test_message = message
				config.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_message', 'updated_at'])
			return Response({'success': True, 'message': message})
		except Exception as exc:
			if config:
				config.last_tested_at = timezone.now()
				config.last_test_status = 'failed'
				config.last_test_message = str(exc)
				config.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_message', 'updated_at'])
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CampaignProgressReportListCreateView(ListCreateAPIView):
	queryset = CampaignProgressReport.objects.none()
	serializer_class = CampaignProgressReportSerializer

	def get_queryset(self):
		return CampaignProgressReport.objects.prefetch_related('campaigns').all()

	@extend_schema(tags=['Email Reports'], summary='List scheduled campaign progress reports', responses={200: CampaignProgressReportSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Email Reports'], summary='Create scheduled campaign progress report', request=CampaignProgressReportSerializer, responses={201: CampaignProgressReportSerializer})
	def post(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = getattr(request, 'user', None)
		instance = serializer.save(created_by=user if getattr(user, 'is_authenticated', False) else None)
		if instance.next_run_at is None:
			instance.next_run_at = timezone.now()
			instance.save(update_fields=['next_run_at', 'updated_at'])
		return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)


class CampaignProgressReportDetailView(RetrieveUpdateDestroyAPIView):
	queryset = CampaignProgressReport.objects.prefetch_related('campaigns').all()
	serializer_class = CampaignProgressReportSerializer

	@extend_schema(tags=['Email Reports'], summary='Get campaign progress report', responses={200: CampaignProgressReportSerializer})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Email Reports'], summary='Replace campaign progress report', request=CampaignProgressReportSerializer, responses={200: CampaignProgressReportSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['Email Reports'], summary='Update campaign progress report', request=CampaignProgressReportSerializer, responses={200: CampaignProgressReportSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['Email Reports'], summary='Delete campaign progress report', responses={204: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class CampaignEmailReportView(APIView):
	@extend_schema(tags=['Email Reports'], summary='Send campaign email report', request=CampaignEmailReportCreateSerializer, responses={201: EmailReportSerializer})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		serializer = CampaignEmailReportCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		payload = serializer.validated_data
		recipients = payload.get('recipients') or campaign.owner_emails or []
		recipients = list(dict.fromkeys(email.strip().lower() for email in recipients if email.strip()))
		if not recipients:
			return Response({'recipients': ['Select recipients or add owner emails to the campaign.']}, status=status.HTTP_400_BAD_REQUEST)
		subject = payload.get('subject') or f'{campaign.name} - Reports'
		log = send_campaign_report(
			campaign=campaign,
			recipients=recipients,
			report_format=payload['format'],
			subject=subject,
			email_config=payload.get('email_config'),
			include_sent_stats=payload['include_sent_stats'],
			include_delivery_stats=payload['include_delivery_stats'],
			include_message_stats=payload['include_message_stats'],
		)
		legacy_report = EmailReport.objects.create(
			campaign=campaign,
			report_type=payload.get('report_type') or payload['format'],
			subject=subject,
			recipients=recipients,
			content=log.content,
			status=log.status,
			sent_at=log.sent_at,
			error_message=log.error_message,
			metadata={'report_delivery_log_id': log.pk, 'report_data': log.report_data},
		)
		return Response(
			{'success': log.status == 'sent', 'data': ReportDeliveryLogSerializer(log).data,
			 'legacy_report_id': legacy_report.pk},
			status=status.HTTP_201_CREATED,
		)


class CampaignEmailReportHistoryView(APIView):
	@extend_schema(tags=['Email Reports'], summary='List email report history for a campaign', responses={200: ReportDeliveryLogSerializer(many=True)})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		queryset = ReportDeliveryLog.objects.filter(campaign=campaign).order_by('-created_at')
		paginator = StandardPagination()
		page = paginator.paginate_queryset(queryset, request)
		return paginator.get_paginated_response(ReportDeliveryLogSerializer(page, many=True).data)


class ReportSubscriptionListCreateView(APIView):
	@extend_schema(tags=['Email Reports'], summary='List report subscriptions')
	def get(self, request):
		queryset = ReportSubscription.objects.select_related('email_config').prefetch_related('campaigns').all()
		active_filter = request.query_params.get('is_active')
		if active_filter is not None:
			if active_filter.lower() not in {'true', 'false'}:
				return Response({'success': False, 'errors': {'is_active': ['Use true or false.']}}, status=status.HTTP_400_BAD_REQUEST)
			queryset = queryset.filter(is_active=(active_filter.lower() == 'true'))
		if frequency := request.query_params.get('frequency'):
			queryset = queryset.filter(frequency=frequency)
		try:
			limit = min(max(int(request.query_params.get('limit', 20)), 1), 100)
			offset = max(int(request.query_params.get('offset', 0)), 0)
		except (TypeError, ValueError):
			return Response({'success': False, 'errors': {'pagination': ['limit and offset must be integers.']}}, status=status.HTTP_400_BAD_REQUEST)
		count = queryset.count()
		rows = queryset.order_by('-created_at', '-id')[offset:offset + limit]
		return Response({
			'success': True,
			'count': count,
			'results': ReportSubscriptionSerializer(rows, many=True).data,
		})

	@extend_schema(tags=['Email Reports'], summary='Create a report subscription', request=ReportSubscriptionSerializer)
	def post(self, request):
		serializer = ReportSubscriptionSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = getattr(request, 'user', None)
		instance = serializer.save(created_by=user if getattr(user, 'is_authenticated', False) else None)
		instance.next_run_at = next_subscription_run_at(instance.frequency, timezone.now())
		instance.save(update_fields=['next_run_at', 'updated_at'])
		return Response(ReportSubscriptionSerializer(instance).data, status=status.HTTP_201_CREATED)


class ReportSubscriptionDetailView(RetrieveUpdateDestroyAPIView):
	queryset = ReportSubscription.objects.select_related('campaign', 'email_config').prefetch_related('campaigns').all()
	serializer_class = ReportSubscriptionSerializer

	def update(self, request, *args, **kwargs):
		partial = kwargs.pop('partial', False)
		instance = self.get_object()
		old_frequency = instance.frequency
		serializer = self.get_serializer(instance, data=request.data, partial=partial)
		serializer.is_valid(raise_exception=True)
		instance = serializer.save()
		if instance.frequency != old_frequency:
			instance.next_run_at = next_subscription_run_at(instance.frequency, timezone.now())
			instance.save(update_fields=['next_run_at', 'updated_at'])
		return Response(self.get_serializer(instance).data)


class ReportSubscriptionDueNowView(APIView):
	@extend_schema(tags=['Email Reports'], summary='List due scheduled report subscriptions')
	def get(self, request):
		now = timezone.now()
		subscriptions = ReportSubscription.objects.filter(
			is_active=True,
			frequency__in=['10min', '1hr', '1day'],
			next_run_at__isnull=False,
			next_run_at__lte=now,
		).order_by('next_run_at', 'id')
		data = [{
			'id': subscription.id,
			'name': subscription.name,
			'frequency': subscription.frequency,
			'next_run_at': subscription.next_run_at.isoformat(),
		} for subscription in subscriptions]
		return Response({'success': True, 'data': data})


class ReportSubscriptionSendNowView(APIView):
	@extend_schema(tags=['Email Reports'], summary='Render and send a report subscription now')
	def post(self, request, pk):
		with transaction.atomic():
			subscription = ReportSubscription.objects.select_for_update(of=('self',)).select_related('email_config').prefetch_related('campaigns').filter(pk=pk).first()
			if subscription is None:
				return Response({'success': False, 'error': 'Subscription not found.'}, status=status.HTTP_404_NOT_FOUND)
			if not subscription.is_active:
				return Response({'success': False, 'error': 'Subscription is inactive.'}, status=status.HTTP_400_BAD_REQUEST)

			now = timezone.now()
			scheduled_value = request.data.get('scheduled', False)
			scheduled_send = scheduled_value is True or str(scheduled_value).strip().lower() in {'true', '1', 'yes'}
			scheduled_slot = subscription.next_run_at

			campaigns_by_id = {
				campaign.id: campaign
				for campaign in subscription.campaigns.filter(
					is_deleted=False,
					status__in=['active', 'in_progress', 'paused'],
				).order_by('id')
			}
			if subscription.campaign_id and not subscription.campaign.is_deleted:
				campaigns_by_id[subscription.campaign_id] = subscription.campaign
			campaigns = [campaigns_by_id[campaign_id] for campaign_id in sorted(campaigns_by_id)]
			if not campaigns:
				return Response({'success': False, 'error': 'Subscription has no campaigns.'}, status=status.HTTP_400_BAD_REQUEST)

			recipients = {
				email.strip().lower()
				for email in (subscription.recipients or [])
				if isinstance(email, str) and email.strip()
			}
			if subscription.include_campaign_owners:
				for campaign in campaigns:
					recipients.update(
						email.strip().lower()
						for email in (campaign.owner_emails or [])
						if isinstance(email, str) and email.strip()
					)
			recipients = sorted(recipients)
			if not recipients:
				return Response({'success': False, 'error': 'Subscription has no recipients.'}, status=status.HTTP_400_BAD_REQUEST)

			if scheduled_send and subscription.next_run_at and subscription.next_run_at > now:
				previous = subscription.delivery_logs.filter(
					status='sent',
					sent_at__gte=now - timedelta(minutes=5),
				).order_by('-sent_at').first()
				if previous:
					return Response({
						'success': True,
						'log_id': previous.id,
						'recipients_count': len(recipients),
						'sent_at': previous.sent_at.isoformat() if previous.sent_at else None,
					})

			previous_successes = []
			recipients_to_send = recipients
			if scheduled_send and scheduled_slot:
				previous_successes = list(subscription.delivery_logs.filter(
					status='sent',
					sent_at__gte=scheduled_slot,
				).order_by('sent_at'))
			already_sent = {
				recipient
				for delivery in previous_successes
				for recipient in (delivery.recipients or [])
			}
			recipients_to_send = [recipient for recipient in recipients if recipient not in already_sent]
			logs = send_subscription_report(subscription, campaigns, recipients_to_send) if recipients_to_send else []
			failed_logs = [delivery for delivery in logs if delivery.status != 'sent']
			if failed_logs:
				return Response({
					'success': False,
					'log_id': failed_logs[0].id,
					'recipients_count': len(recipients),
					'error': '; '.join(delivery.error_message for delivery in failed_logs),
				})

			success_logs = previous_successes + [delivery for delivery in logs if delivery.status == 'sent']
			sent_at = max((delivery.sent_at for delivery in success_logs if delivery.sent_at), default=now)
			subscription.last_sent_at = sent_at
			update_fields = ['last_sent_at', 'updated_at']
			if scheduled_send and subscription.frequency != 'manual':
				subscription.next_run_at = next_subscription_run_at(subscription.frequency, now)
				update_fields.append('next_run_at')
			subscription.save(update_fields=update_fields)
			return Response({
				'success': True,
				'log_id': logs[0].id if logs else (previous_successes[0].id if previous_successes else None),
				'recipients_count': len(recipients),
				'sent_at': sent_at.isoformat(),
			})


class ReportDeliveryLogDetailView(APIView):
	@extend_schema(tags=['Email Reports'], summary='Read a report delivery log', responses={200: ReportDeliveryLogSerializer})
	def get(self, request, pk):
		log = get_object_or_404(ReportDeliveryLog, pk=pk)
		return Response(ReportDeliveryLogSerializer(log).data)


class EmailReportResendView(APIView):
	@extend_schema(tags=['Email Reports'], summary='Resend a failed email report', responses={200: ReportDeliveryLogSerializer})
	def post(self, request, pk):
		log = get_object_or_404(ReportDeliveryLog, pk=pk)
		if log.status != 'failed':
			return Response({'detail': 'Only failed report deliveries can be resent.'}, status=status.HTTP_400_BAD_REQUEST)
		if log.campaign is None:
			return Response({'detail': 'The campaign for this report is no longer available.'}, status=status.HTTP_400_BAD_REQUEST)
		log = send_campaign_report(
			campaign=log.campaign,
			recipients=log.recipients,
			report_format=log.format,
			subject=log.subject,
			include_sent_stats=log.include_sent_stats,
			include_delivery_stats=log.include_delivery_stats,
			include_message_stats=log.include_message_stats,
			email_config=log.email_config,
			subscription=log.subscription,
			log=log,
		)
		return Response({'success': log.status == 'sent', 'data': ReportDeliveryLogSerializer(log).data})


class SentRecordListCreateView(APIView):
	@extend_schema(tags=['Sent Tracker'], summary='List sent records', responses={200: SentRecordSerializer(many=True)})
	def get(self, request):
		queryset = SentRecord.objects.all()
		for parameter in ('campaign_id', 'batch_id', 'sent_status', 'msisdn'):
			value = request.query_params.get(parameter)
			if value:
				queryset = queryset.filter(**{parameter: value})
		paginator = StandardPagination()
		page = paginator.paginate_queryset(queryset, request)
		return paginator.get_paginated_response(SentRecordSerializer(page, many=True).data)

	@extend_schema(tags=['Sent Tracker'], summary='Create sent record', request=SentRecordCreateSerializer, responses={201: SentRecordSerializer})
	def post(self, request):
		serializer = SentRecordCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		record = SentTrackerService.create_single(serializer.validated_data)
		return Response({'success': True, 'data': SentRecordSerializer(record).data}, status=status.HTTP_201_CREATED)


class SentRecordDetailView(APIView):
	def get_object(self, pk):
		return get_object_or_404(SentRecord, pk=pk)

	@extend_schema(tags=['Sent Tracker'], summary='Get sent record', responses={200: SentRecordSerializer})
	def get(self, request, pk):
		return Response({'success': True, 'data': SentRecordSerializer(self.get_object(pk)).data})

	@extend_schema(tags=['Sent Tracker'], summary='Update sent status', request=SentRecordUpdateSerializer, responses={200: SentRecordSerializer})
	def patch(self, request, pk):
		record = self.get_object(pk)
		serializer = SentRecordUpdateSerializer(record, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		record = serializer.save()
		return Response({'success': True, 'data': SentRecordSerializer(record).data})

	@extend_schema(tags=['Sent Tracker'], summary='Delete sent record', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, pk):
		self.get_object(pk).delete()
		return Response({'success': True, 'message': 'Sent record deleted.'})


class SentRecordBulkCreateView(APIView):
	@extend_schema(tags=['Sent Tracker'], summary='Bulk create sent records', request=SentRecordBulkCreateSerializer, responses={201: OpenApiResponse(description='Bulk result.')})
	def post(self, request):
		serializer = SentRecordBulkCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		return Response({'success': True, 'data': SentTrackerService.bulk_create(serializer.validated_data['records'])}, status=status.HTTP_201_CREATED)


class SentRecordBulkUpdateView(APIView):
	@extend_schema(tags=['Sent Tracker'], summary='Bulk update sent statuses', request=SentRecordBulkUpdateSerializer, responses={200: OpenApiResponse(description='Bulk result.')})
	def post(self, request):
		serializer = SentRecordBulkUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		return Response({'success': True, 'data': SentTrackerService.bulk_update_status(serializer.validated_data['updates'])})


class CampaignSentRecordsView(APIView):
	@extend_schema(tags=['Sent Tracker'], summary='List campaign sent records', responses={200: SentRecordSerializer(many=True)})
	def get(self, request, campaign_id):
		get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		queryset = SentRecord.objects.filter(campaign_id=campaign_id)
		for parameter in ('sent_status', 'batch_id'):
			value = request.query_params.get(parameter)
			if value:
				queryset = queryset.filter(**{parameter: value})
		paginator = StandardPagination()
		page = paginator.paginate_queryset(queryset, request)
		return paginator.get_paginated_response(SentRecordSerializer(page, many=True).data)


class CampaignSentStatsView(APIView):
	@extend_schema(tags=['Sent Tracker'], summary='Get campaign sent statistics', responses={200: OpenApiResponse(description='Sent statistics.')})
	def get(self, request, campaign_id):
		get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		return Response({'success': True, 'data': SentTrackerService.get_campaign_stats(campaign_id)})


class CustomerProfileConfigListCreateView(ListCreateAPIView):
	queryset = CustomerProfileConfig.objects.all()
	serializer_class = CustomerProfileConfigSerializer
	@extend_schema(tags=['Customer Profile Config'], summary='List customer profile configurations', responses={200: CustomerProfileConfigSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Customer Profile Config'], summary='Create customer profile configuration', request=CustomerProfileConfigSerializer, responses={201: CustomerProfileConfigSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)


class CustomerProfileConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = CustomerProfileConfig.objects.all()
	serializer_class = CustomerProfileConfigSerializer

	@extend_schema(tags=['Customer Profile Config'], summary='Get customer profile configuration', responses={200: CustomerProfileConfigSerializer})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Customer Profile Config'], summary='Replace customer profile configuration', request=CustomerProfileConfigSerializer, responses={200: CustomerProfileConfigSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['Customer Profile Config'], summary='Update customer profile configuration', request=CustomerProfileConfigSerializer, responses={200: CustomerProfileConfigSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['Customer Profile Config'], summary='Delete customer profile configuration', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class CampaignAudienceView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get campaign audience summary', responses={200: OpenApiResponse(description='Campaign audience summary.')})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		config = AudienceConfig.objects.filter(campaign=campaign).select_related('default_language').first()
		try:
			round_number = int(request.query_params.get('round_number') or (config.round_number if config else 1))
		except (TypeError, ValueError):
			return Response({'detail': 'round_number must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
		members = AudienceMember.objects.filter(campaign=campaign, round_number=round_number)
		counts = members.aggregate(
			total=Count('id'), valid=Count('id', filter=Q(is_valid=True)),
			invalid=Count('id', filter=Q(is_valid=False)), built_at=Max('rebuilt_at'),
		)
		language_breakdown = list(members.values('language__code').annotate(count=Count('id')).order_by('language__code'))
		language_sources = dict(members.values_list('language_source').annotate(count=Count('id')))
		return Response({'success': True, 'data': {
			'campaign_id': campaign.id,
			'default_language': config.default_language.code if config else None,
			'source_type': config.source_type if config else None,
			'source_config': {},
			'main_database': config.source_database_id if config else None,
			'main_table': config.source_table if config else '',
			'main_msisdn_column': config.source_msisdn_column if config else '',
			'main_language_column': config.source_language_column if config else '',
			'file_path': config.source_file_path if config else '',
			'file_msisdn_column': config.source_file_msisdn_column if config else '',
			'file_language_column': config.source_file_language_column if config else '',
			'customer_profile': None,
			'round_number': round_number,
			'total_count': counts['total'],
			'valid_count': counts['valid'],
			'invalid_count': counts['invalid'],
			'language_matched': language_sources.get('source', 0) + language_sources.get('mapper', 0),
			'language_defaulted': language_sources.get('default', 0),
			'language_breakdown': [{'language': item['language__code'], 'count': item['count']} for item in language_breakdown],
			'built_at': counts['built_at'],
			'is_processed': config.is_processed if config else False,
			'processing_started_at': None,
			'processing_completed_at': config.last_built_at if config else None,
		}})

	@extend_schema(tags=['Audience Management'], summary='Add manual campaign audience', request=ManualAudienceInputSerializer, responses={201: OpenApiResponse(description='Campaign audience summary.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		serializer = ManualAudienceInputSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		profile = None
		profile_id = serializer.validated_data.get('customer_profile_id')
		if profile_id:
			profile = get_object_or_404(CustomerProfileConfig, id=profile_id, is_active=True)
		campaign = AudienceService(campaign, serializer.validated_data['default_language'], profile).create_from_manual(
			serializer.validated_data['msisdns'],
			serializer.validated_data.get('languages'),
			serializer.validated_data['source_type'],
		)
		config = AudienceConfig.objects.filter(campaign=campaign).select_related('default_language').first()
		return Response({'success': True, 'data': {
			'campaign_id': campaign.id,
			'default_language': config.default_language.code if config else None,
			'source_type': config.source_type if config else None,
			'source_config': {},
			'main_database': config.source_database_id if config else None,
			'main_table': config.source_table if config else '',
			'main_msisdn_column': config.source_msisdn_column if config else '',
			'main_language_column': config.source_language_column if config else '',
			'file_path': config.source_file_path if config else '',
			'file_msisdn_column': config.source_file_msisdn_column if config else '',
			'file_language_column': config.source_file_language_column if config else '',
			'customer_profile': None,
			'total_count': config.total_count if config else 0,
			'valid_count': config.valid_count if config else 0,
			'invalid_count': config.invalid_count if config else 0,
			'language_matched': (config.language_from_source + config.language_from_mapper) if config else 0,
			'language_defaulted': config.language_from_default if config else 0,
			'is_processed': config.is_processed if config else False,
			'processing_started_at': None,
			'processing_completed_at': config.last_built_at if config else None,
		}}, status=status.HTTP_201_CREATED)


class ManualAudienceApiView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Create manual audience configuration', request=ManualAudienceSerializer, responses={201: OpenApiResponse(description='Manual audience configured.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		serializer = ManualAudienceSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			config = AudienceConfig(campaign=campaign)
		config.source_type = 'manual'
		config.manual_msisdns = data['manual_msisdns']
		config.manual_languages = data.get('manual_languages', [])
		config.source_file_path = ''
		config.source_file_msisdn_column = ''
		config.source_file_language_column = ''
		config.source_database = None
		config.source_table = ''
		config.source_filter_clause = ''
		config.mapper_enabled = data.get('mapper_enabled', False)
		config.mapper_database_id = data.get('mapper_database_id')
		config.mapper_table = data.get('mapper_table', '')
		config.mapper_msisdn_column = data.get('mapper_msisdn_column', '')
		config.mapper_language_column = data.get('mapper_language_column', '')
		config.mapper_join_type = data.get('mapper_join_type', 'LEFT')
		config.rebuild_before_each_run = data.get('rebuild_before_each_run', data.get('rebuild_on_each_round', False))
		config.rebuild_on_each_round = data.get('rebuild_on_each_round', config.rebuild_before_each_run)
		config.rebuild_minutes_before = data.get('rebuild_minutes_before', 10)
		config.rebuild_timeout_minutes = data.get('rebuild_timeout_minutes', 30)
		config.default_language_id = data['default_language_id']
		config.save()
		logger.info(
			'Audience configuration saved campaign_id=%s config_id=%s source_type=manual recipient_count=%s',
			campaign.pk, config.pk, len(config.manual_msisdns),
		)
		return Response({'success': True, 'message': 'Manual audience configured.', 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class FileAudienceApiView(APIView):
	parser_classes = [MultiPartParser, FormParser]

	@extend_schema(tags=['Audience Management'], summary='Create file-import audience configuration', request=FileAudienceSerializer, responses={201: OpenApiResponse(description='File audience configured.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		serializer = FileAudienceSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			config = AudienceConfig(campaign=campaign)
		upload = data['file']
		stored_path = default_storage.save(
			f'audience/{uuid.uuid4()}_{os.path.basename(upload.name)}',
			upload,
		)
		config.source_type = 'file_import'
		config.manual_msisdns = []
		config.manual_languages = []
		config.source_database = None
		config.source_table = ''
		config.source_filter_clause = ''
		config.source_file_path = default_storage.path(stored_path)
		config.source_file_msisdn_column = data['source_file_msisdn_column']
		config.source_file_language_column = data.get('source_file_language_column', '')
		config.mapper_enabled = data.get('mapper_enabled', False)
		config.mapper_database_id = data.get('mapper_database_id')
		config.mapper_table = data.get('mapper_table', '')
		config.mapper_msisdn_column = data.get('mapper_msisdn_column', '')
		config.mapper_language_column = data.get('mapper_language_column', '')
		config.mapper_join_type = data.get('mapper_join_type', 'LEFT')
		config.rebuild_before_each_run = data.get('rebuild_before_each_run', data.get('rebuild_on_each_round', False))
		config.rebuild_on_each_round = data.get('rebuild_on_each_round', config.rebuild_before_each_run)
		config.rebuild_minutes_before = data.get('rebuild_minutes_before', 10)
		config.rebuild_timeout_minutes = data.get('rebuild_timeout_minutes', 30)
		config.default_language_id = data['default_language_id']
		config.save()
		logger.info(
			'Audience configuration saved campaign_id=%s config_id=%s source_type=file_import file_name=%s msisdn_column=%s language_column=%s',
			campaign.pk, config.pk, os.path.basename(upload.name),
			config.source_file_msisdn_column, config.source_file_language_column or None,
		)
		return Response({'success': True, 'message': 'File audience configured.', 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class DatabaseAudienceApiView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Create database audience configuration', request=DatabaseAudienceSerializer, responses={201: OpenApiResponse(description='Database audience configured.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		serializer = DatabaseAudienceSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			config = AudienceConfig(campaign=campaign)
		config.source_type = 'database'
		config.manual_msisdns = []
		config.manual_languages = []
		config.source_file_path = ''
		config.source_file_msisdn_column = ''
		config.source_file_language_column = ''
		config.source_database_id = data['source_database_id']
		config.source_table = data['source_table']
		config.source_msisdn_column = data['source_msisdn_column']
		config.source_language_column = data.get('source_language_column', '')
		config.source_filter_clause = data.get('source_filter_clause', '')
		config.mapper_enabled = data.get('mapper_enabled', False)
		config.mapper_database_id = data.get('mapper_database_id')
		config.mapper_table = data.get('mapper_table', '')
		config.mapper_msisdn_column = data.get('mapper_msisdn_column', '')
		config.mapper_language_column = data.get('mapper_language_column', '')
		config.mapper_join_type = data.get('mapper_join_type', 'LEFT')
		config.rebuild_before_each_run = data.get('rebuild_before_each_run', data.get('rebuild_on_each_round', False))
		config.rebuild_on_each_round = data.get('rebuild_on_each_round', config.rebuild_before_each_run)
		config.rebuild_minutes_before = data.get('rebuild_minutes_before', 10)
		config.rebuild_timeout_minutes = data.get('rebuild_timeout_minutes', 30)
		config.default_language_id = data['default_language_id']
		config.save()
		logger.info(
			'Audience configuration saved campaign_id=%s config_id=%s source_type=database database_id=%s table=%s msisdn_column=%s language_column=%s',
			campaign.pk, config.pk, config.source_database_id, config.source_table,
			config.source_msisdn_column, config.source_language_column or None,
		)
		return Response({'success': True, 'message': 'Database audience configured.', 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class AudienceBuildView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Start asynchronous audience build', responses={202: OpenApiResponse(description='Audience build started.')})
	def post(self, request, pk):
		config = get_object_or_404(AudienceConfig, id=pk)
		if config.campaign.status not in {'draft', 'active', 'paused'}:
			logger.warning(
				'Audience build rejected config_id=%s campaign_id=%s campaign_status=%s',
				config.pk, config.campaign_id, config.campaign.status,
			)
			return Response({'detail': 'Audience rebuilds are allowed only for draft, active, or paused campaigns.'}, status=status.HTTP_400_BAD_REQUEST)
		requested_round = request.data.get('target_round', request.data.get('round_number'))
		try:
			if requested_round is not None:
				target_round = int(requested_round)
			elif request.data.get('increment_round'):
				target_round = max(config.round_number, 1) + 1
			else:
				target_round = max(config.round_number, 1)
		except (TypeError, ValueError):
			logger.warning('Audience build rejected config_id=%s invalid_round=%r', config.pk, requested_round)
			return Response({'success': False, 'detail': 'round_number must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
		if target_round < 1:
			logger.warning('Audience build rejected config_id=%s invalid_round=%s', config.pk, target_round)
			return Response({'success': False, 'detail': 'target_round must be at least 1.'}, status=status.HTTP_400_BAD_REQUEST)
		try:
			with transaction.atomic():
				config = AudienceConfig.objects.select_for_update().get(pk=config.pk)
				if AudienceBuildJob.objects.filter(
					audience_config=config, status__in=['PENDING', 'RUNNING'],
				).exists():
					logger.warning('Audience build already active config_id=%s campaign_id=%s', config.pk, config.campaign_id)
					return Response({'success': False, 'detail': 'A build is already running.'}, status=status.HTTP_409_CONFLICT)
				build_id = uuid.uuid4().hex
				job = AudienceBuildJob.objects.create(
					audience_config=config,
					round_number=target_round,
					result={'build_id': build_id},
				)
				config.last_rebuild_status = 'running'
				config.last_rebuild_phase = 'starting'
				config.round_number = target_round
				config.last_build_id = build_id
				config.last_rebuild_processed = 0
				config.last_rebuild_total = 0
				config.last_rebuild_percent = 0
				config.last_rebuild_started_at = timezone.now()
				config.last_rebuild_error = ''
				config.save(update_fields=[
					'last_rebuild_status', 'last_rebuild_phase', 'round_number', 'last_build_id', 'last_rebuild_processed',
					'last_rebuild_total', 'last_rebuild_percent', 'last_rebuild_started_at',
					'last_rebuild_error', 'updated_at',
				])
		except IntegrityError:
			logger.warning('Audience build concurrency conflict config_id=%s campaign_id=%s', config.pk, config.campaign_id)
			return Response({'success': False, 'detail': 'A build is already running.'}, status=status.HTTP_409_CONFLICT)

		logger.info(
			'Audience build queued job_id=%s config_id=%s campaign_id=%s round=%s',
			job.pk, config.pk, config.campaign_id, target_round,
		)
		return Response({
			'success': True,
			'message': 'Build queued.',
			'config_id': config.id,
			'job_id': job.id,
			'target_round': target_round,
			'round_number': target_round,
		}, status=status.HTTP_202_ACCEPTED)


class AudienceConfigProgressView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get audience build progress', responses={200: OpenApiResponse(description='Progress snapshot.')})
	def get(self, request, pk):
		config = get_object_or_404(AudienceConfig, id=pk)
		active_job = config.build_jobs.filter(status__in=['PENDING', 'RUNNING']).order_by('-created_at').first()
		return Response({'success': True, 'data': {
			'config_id': config.id,
			'round_number': active_job.round_number if active_job else config.round_number,
			'build_id': config.last_build_id,
			'status': config.last_rebuild_status,
			'phase': config.last_rebuild_phase,
			'processed': config.last_rebuild_processed,
			'total': config.last_rebuild_total,
			'percent': float(config.last_rebuild_percent or 0),
			'started_at': config.last_rebuild_started_at,
			'completed_at': config.last_rebuild_completed_at,
			'duration_seconds': config.last_rebuild_duration_seconds,
			'error': config.last_rebuild_error or None,
			'counters': {
				'valid': config.valid_count,
				'invalid': config.invalid_count,
				'from_source': config.language_from_source,
				'from_mapper': config.language_from_mapper,
				'from_default': config.language_from_default,
			},
		}})


class AudienceBuildJobView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get audience build job status', responses={200: OpenApiResponse(description='Audience build job status.')})
	def get(self, request, pk):
		job = get_object_or_404(AudienceBuildJob, pk=pk)
		return Response({'success': True, 'data': {
			'id': job.id, 'audience_config_id': job.audience_config_id, 'status': job.status,
			'processed_rows': job.processed_rows, 'valid_rows': job.valid_rows,
			'invalid_rows': job.invalid_rows, 'started_at': job.started_at,
			'heartbeat_at': job.heartbeat_at, 'completed_at': job.completed_at,
			'error_message': job.error_message, 'result': job.result,
		}})


class AudienceConfigCreateView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get campaign audience config metadata', responses={200: AudienceConfigSerializer})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			return Response({'success': True, 'data': None})
		return Response({'success': True, 'data': AudienceConfigSerializer(config).data})

	@extend_schema(tags=['Audience Management'], summary='Create or update campaign audience metadata config', request=AudienceConfigSerializer, responses={201: AudienceConfigSerializer})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status != 'draft':
			return Response(
				{'detail': 'Only draft campaigns can be edited.'},
				status=status.HTTP_400_BAD_REQUEST,
			)
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			default_language_id = request.data.get('default_language_id')
			if not default_language_id:
				return Response(
					{'default_language_id': ['This field is required.']},
					status=status.HTTP_400_BAD_REQUEST,
				)
			config = AudienceConfig(
				campaign=campaign,
				default_language_id=default_language_id,
			)
		serializer = AudienceConfigSerializer(config, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response({'success': True, 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class AudienceConfigPreviewView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Preview campaign audience metadata as a JOIN-ready SQL sketch', responses={200: OpenApiResponse(description='Preview result.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status != 'draft':
			return Response({'detail': 'Only draft campaigns can have their audience changed.'}, status=status.HTTP_400_BAD_REQUEST)
		config, _ = AudienceConfig.objects.get_or_create(campaign=campaign)
		serializer = AudienceConfigSerializer(config, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		rows = []
		for row in range(3):
			rows.append({
				'msisdn': f'+2517000000{row}',
				'language': 'en' if row == 0 else 'am',
				'language_source': 'mapper' if row == 0 else 'source',
			})
		return Response({
			'success': True,
			'data': {
				'campaign_id': campaign.id,
				'source_type': config.source_type,
				'sql': (
					f'SELECT src.{config.source_msisdn_column or "msisdn"} AS msisdn, '
					f'COALESCE(src.{config.source_language_column or "language"}, map.{config.mapper_language_column or "language"}) AS language '
					f'FROM {config.source_table or "source_table"} src '
					f'{config.mapper_join_type or "LEFT"} JOIN {config.mapper_table or "mapper_table"} map '
					f'ON src.{config.source_msisdn_column or "msisdn"} = map.{config.mapper_msisdn_column or "msisdn"}'
				),
				'sample_rows': rows,
				'stats_preview': {
					'total': len(rows),
					'from_source': 1,
					'from_mapper': 2,
					'from_default': 0,
				},
			},
		})


class CampaignAudienceMembersView(APIView):
	@extend_schema(tags=['Audience Management'], summary='List campaign audience members', responses={200: AudienceMemberSerializer(many=True)})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		try:
			round_number = int(request.query_params.get('round_number') or (config.round_number if config else 1))
		except (TypeError, ValueError):
			return Response({'detail': 'round_number must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
		members = AudienceMember.objects.filter(campaign=campaign, round_number=round_number).order_by('sequence_number')
		paginator = StandardPagination()
		page = paginator.paginate_queryset(members, request)
		return paginator.get_paginated_response(AudienceMemberSerializer(page, many=True).data)


class CampaignAudienceRoundsView(APIView):
	@extend_schema(tags=['Audience Management'], summary='List built audience rounds', responses={200: OpenApiResponse(description='Audience rounds.')})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		rounds = AudienceMember.objects.filter(campaign=campaign).values('round_number').annotate(
			rows=Count('id'), built_at=Max('rebuilt_at'),
		).order_by('-round_number')
		return Response([{
			'round_number': row['round_number'],
			'rows': row['rows'],
			'built_at': row['built_at'],
		} for row in rounds])


class CampaignReadinessView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Check campaign readiness', responses={200: CampaignReadinessSerializer})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		return Response({'success': True, 'data': CampaignReadinessService(campaign).check()})


class CampaignValidateView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Validate campaign', request=None, responses={200: CampaignReadinessSerializer})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		return Response({'success': True, 'data': CampaignActionsService(campaign).validate_campaign()})


class CampaignActivateView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Activate campaign', request=None, responses={200: OpenApiResponse(description='Activation result.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status in {'active', 'in_progress'}:
			return Response({
				'success': True,
				'message': 'Campaign is already active.',
				'data': {
					'campaign_id': campaign.id,
					'status': campaign.status,
					'messages_built': 0,
				},
			})
		build = request.data.get('build_messages', True)
		if isinstance(build, str):
			build = build.lower() not in ('false', '0', 'no')
		result = CampaignActionsService(campaign).activate_campaign(bool(build))
		if result['success'] and getattr(request.user, 'is_authenticated', False):
			campaign.activated_by = request.user
			campaign.save(update_fields=['activated_by', 'updated_at'])
		return Response(result, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)


class CampaignStartView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Start an active campaign', request=None, responses={200: OpenApiResponse(description='Start result.')})
	def post(self, request, campaign_id):
		return _campaign_action_response(campaign_id, 'start_campaign')


class CampaignSendNowView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Start the SMS sender immediately', request=None, responses={202: OpenApiResponse(description='Sender started.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		if campaign.status not in {'active', 'in_progress', 'paused', 'stopped'}:
			return Response(
				{'success': False, 'message': f"Cannot start sender for campaign in '{campaign.status}' status."},
				status=status.HTTP_400_BAD_REQUEST,
			)
		if not campaign.is_ready_to_execute:
			return Response(
				{'success': False, 'message': 'Campaign is not ready to execute.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if not campaign.messages.filter(sent_status__in=['PENDING', 'FAILED']).exists():
			return Response(
				{'success': False, 'message': 'Campaign has no queued messages to send.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		was_stopped = campaign.status == 'stopped'
		if was_stopped:
			campaign.status = 'active'
			campaign.activated_at = timezone.now()
			campaign.save(update_fields=['status', 'activated_at', 'updated_at'])

		round_number = Schedule.objects.filter(campaign=campaign).values_list('current_round', flat=True).first() or 1
		try:
			sender_response = requests.post(
				f'{settings.SMSC_SENDER_API}/sender/start',
				json={'campaign_id': campaign.pk, 'round_number': round_number},
				timeout=30,
			)
			body = sender_response.json()
		except requests.RequestException as exc:
			return Response(
				{'success': False, 'message': f'SMS sender is unavailable: {exc}'},
				status=status.HTTP_503_SERVICE_UNAVAILABLE,
			)
		except ValueError:
			body = {'detail': sender_response.text[:500]}

		if sender_response.status_code == 409:
			return Response({'success': True, 'message': 'Campaign sender is already running.', 'data': body})
		if sender_response.status_code != 202 or body.get('success') is False:
			if was_stopped:
				campaign.status = 'stopped'
				campaign.save(update_fields=['status', 'updated_at'])
			return Response(
				{'success': False, 'message': body.get('detail') or 'SMS sender rejected the campaign.', 'data': body},
				status=status.HTTP_502_BAD_GATEWAY,
			)
		return Response({'success': True, 'message': 'Campaign sender started.', 'data': body.get('data', body)}, status=status.HTTP_202_ACCEPTED)


class CampaignPauseView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Pause campaign', request=None, responses={200: OpenApiResponse(description='Pause result.')})
	def post(self, request, campaign_id):
		return _campaign_action_response(campaign_id, 'pause_campaign')


class CampaignResumeView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Resume campaign', request=None, responses={200: OpenApiResponse(description='Resume result.')})
	def post(self, request, campaign_id):
		return _campaign_action_response(campaign_id, 'resume_campaign')


class CampaignCompleteView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Complete campaign', request=None, responses={200: OpenApiResponse(description='Completion result.')})
	def post(self, request, campaign_id):
		return _campaign_action_response(campaign_id, 'complete_campaign')


class CampaignCancelView(APIView):
	@extend_schema(tags=['Campaign Actions'], summary='Cancel campaign', request=None, responses={200: OpenApiResponse(description='Cancellation result.')})
	def post(self, request, campaign_id):
		return _campaign_action_response(campaign_id, 'cancel_campaign')


def _campaign_action_response(campaign_id, action):
	campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
	result = getattr(CampaignActionsService(campaign), action)()
	return Response(result, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)

@extend_schema_view(
	get=extend_schema(tags=['Delivery Tracker'], summary='List delivery records', responses={200: DeliveryRecordSerializer(many=True)}),
	post=extend_schema(tags=['Delivery Tracker'], summary='Create delivery record', request=DeliveryRecordCreateSerializer, responses={201: DeliveryRecordSerializer}),
)
class DeliveryRecordListCreateView(APIView):
	def get(self, request):
		queryset = DeliveryRecord.objects.all()
		for parameter in ('campaign_id', 'batch_id', 'delivery_status', 'msisdn'):
			value = request.query_params.get(parameter)
			if value:
				queryset = queryset.filter(**{parameter: value})
		paginator = StandardPagination()
		page = paginator.paginate_queryset(queryset.order_by('-created_at'), request)
		return paginator.get_paginated_response(DeliveryRecordSerializer(page, many=True).data)

	def post(self, request):
		serializer = DeliveryRecordCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		record = DeliveryTrackerService.create_single(serializer.validated_data)
		return Response({'success': True, 'data': DeliveryRecordSerializer(record).data}, status=status.HTTP_201_CREATED)


class DeliveryReportCallbackView(APIView):
	"""Receive provider delivery reports and persist them idempotently."""

	@extend_schema(tags=['Delivery Tracker'], summary='Receive SMSC delivery report', request=None, responses={200: OpenApiResponse(description='Delivery report accepted.')})
	def post(self, request):
		provider_message_id = str(request.data.get('provider_message_id') or '').strip()
		provider_status = str(request.data.get('status') or '').strip().upper()
		if not provider_message_id or not provider_status:
			return Response(
				{'success': False, 'message': 'provider_message_id and status are required.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		status_map = {
			'DELIVRD': 'DELIVERED',
			'UNDELIV': 'UNDELIVERABLE',
			'EXPIRED': 'EXPIRED',
			'REJECTD': 'REJECTED',
		}
		mapped_status = status_map.get(provider_status, 'UNKNOWN')
		delivered_at = request.data.get('delivered_at')
		if delivered_at:
			delivered_at = parse_datetime(str(delivered_at))
			if delivered_at is None:
				return Response(
					{'success': False, 'message': 'Invalid delivered_at timestamp.'},
					status=status.HTTP_400_BAD_REQUEST,
				)

		with transaction.atomic():
			sent_record = SentRecord.objects.select_related('campaign', 'channel').select_for_update().filter(
				provider_message_id=provider_message_id,
			).first()
			if sent_record is None:
				return Response(
					{'success': False, 'message': 'Unknown provider_message_id.'},
					status=status.HTTP_404_NOT_FOUND,
				)

			sent_record.provider_status = provider_status
			sent_record.provider_response = dict(request.data)
			sent_record.save(update_fields=['provider_status', 'provider_response', 'updated_at'])

			defaults = {
				'campaign': sent_record.campaign,
				'channel': sent_record.channel,
				'message_object': None,
				'sent_record': sent_record,
				'msisdn': str(request.data.get('receiver') or sent_record.msisdn),
				'batch_id': sent_record.batch_id,
				'delivered_at': delivered_at if mapped_status == 'DELIVERED' else None,
				'delivery_status': mapped_status,
				'provider_status': provider_status,
				'provider_response': dict(request.data),
				'error_message': str(request.data.get('error_reason') or ''),
			}
			record = DeliveryRecord.objects.filter(sent_record=sent_record).order_by('-id').first()
			if record is not None and record.is_terminal():
				return Response({
					'success': True,
					'delivery_record_id': record.id,
					'delivery_status': record.delivery_status,
				})
			if record is None:
				record = DeliveryRecord.objects.create(**defaults)
			else:
				for field, value in defaults.items():
					setattr(record, field, value)
				record.save(update_fields=[
					'delivered_at', 'delivery_status', 'provider_status',
					'provider_response', 'error_message', 'updated_at',
				])

		return Response({
			'success': True,
			'delivery_record_id': record.id,
			'delivery_status': record.delivery_status,
		})


@extend_schema_view(
	get=extend_schema(tags=['Delivery Tracker'], summary='Get delivery record', responses={200: DeliveryRecordSerializer}),
	patch=extend_schema(tags=['Delivery Tracker'], summary='Update delivery status', request=DeliveryRecordUpdateSerializer, responses={200: DeliveryRecordSerializer}),
	delete=extend_schema(tags=['Delivery Tracker'], summary='Delete delivery record', responses={200: OpenApiResponse(description='Deleted.')}),
)
class DeliveryRecordDetailView(APIView):
	def get_object(self, pk):
		return get_object_or_404(DeliveryRecord, pk=pk)

	def get(self, request, pk):
		return Response({'success': True, 'data': DeliveryRecordSerializer(self.get_object(pk)).data})

	def patch(self, request, pk):
		record = self.get_object(pk)
		serializer = DeliveryRecordUpdateSerializer(record, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		record = serializer.save()
		return Response({'success': True, 'data': DeliveryRecordSerializer(record).data})

	def delete(self, request, pk):
		self.get_object(pk).delete()
		return Response({'success': True, 'message': 'Delivery record deleted.'})


class DeliveryRecordBulkCreateView(APIView):
	@extend_schema(tags=['Delivery Tracker'], summary='Bulk create delivery records', request=DeliveryRecordBulkCreateSerializer, responses={201: OpenApiResponse(description='Bulk result.')})
	def post(self, request):
		serializer = DeliveryRecordBulkCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		result = DeliveryTrackerService.bulk_create(serializer.validated_data['records'])
		return Response({'success': True, 'data': result}, status=status.HTTP_201_CREATED)


class DeliveryRecordBulkUpdateView(APIView):
	@extend_schema(tags=['Delivery Tracker'], summary='Bulk update delivery statuses', request=DeliveryRecordBulkUpdateSerializer, responses={200: OpenApiResponse(description='Bulk result.')})
	def post(self, request):
		serializer = DeliveryRecordBulkUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		result = DeliveryTrackerService.bulk_update_status(serializer.validated_data['updates'])
		return Response({'success': True, 'data': result})


class CampaignDeliveryRecordsView(APIView):
	@extend_schema(tags=['Delivery Tracker'], summary='List campaign delivery records', responses={200: DeliveryRecordSerializer(many=True)})
	def get(self, request, campaign_id):
		get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		queryset = DeliveryRecord.objects.filter(campaign_id=campaign_id)
		for parameter in ('delivery_status', 'batch_id'):
			value = request.query_params.get(parameter)
			if value:
				queryset = queryset.filter(**{parameter: value})
		paginator = StandardPagination()
		page = paginator.paginate_queryset(queryset.order_by('-created_at'), request)
		return paginator.get_paginated_response(DeliveryRecordSerializer(page, many=True).data)


class CampaignDeliveryStatsView(APIView):
	@extend_schema(tags=['Delivery Tracker'], summary='Get campaign delivery statistics', responses={200: OpenApiResponse(description='Delivery statistics.')})
	def get(self, request, campaign_id):
		get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		return Response({'success': True, 'data': DeliveryTrackerService.get_campaign_stats(campaign_id)})


class DatabaseConfigListCreateView(APIView):
	@extend_schema(tags=['Database Config'], summary='List database configurations', responses={200: DatabaseConfigSerializer(many=True)})
	def get(self, request):
		queryset = DatabaseConfig.objects.all()
		database_type = request.query_params.get('database_type')
		if database_type:
			queryset = queryset.filter(database_type=database_type)
		return Response({'success': True, 'data': DatabaseConfigSerializer(queryset, many=True).data})

	@extend_schema(tags=['Database Config'], summary='Create database configuration', request=DatabaseConfigCreateUpdateSerializer, responses={201: DatabaseConfigSerializer})
	def post(self, request):
		serializer = DatabaseConfigCreateUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		config = serializer.save(created_by=request.user if request.user.is_authenticated else None)
		return Response({'success': True, 'data': DatabaseConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class DatabaseConfigDetailView(APIView):
	def _config(self, pk):
		return get_object_or_404(DatabaseConfig, pk=pk)

	@extend_schema(tags=['Database Config'], summary='Get database configuration', responses={200: DatabaseConfigSerializer})
	def get(self, request, pk):
		return Response({'success': True, 'data': DatabaseConfigSerializer(self._config(pk)).data})

	def _update(self, request, pk, partial):
		config = self._config(pk)
		serializer = DatabaseConfigCreateUpdateSerializer(config, data=request.data, partial=partial)
		serializer.is_valid(raise_exception=True)
		config = serializer.save()
		return Response({'success': True, 'data': DatabaseConfigSerializer(config).data})

	@extend_schema(tags=['Database Config'], summary='Replace database configuration', request=DatabaseConfigCreateUpdateSerializer, responses={200: DatabaseConfigSerializer})
	def put(self, request, pk):
		return self._update(request, pk, False)

	@extend_schema(tags=['Database Config'], summary='Update database configuration', request=DatabaseConfigCreateUpdateSerializer, responses={200: DatabaseConfigSerializer})
	def patch(self, request, pk):
		return self._update(request, pk, True)

	@extend_schema(tags=['Database Config'], summary='Delete database configuration', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, pk):
		self._config(pk).delete()
		return Response({'success': True, 'message': 'Database configuration deleted successfully.'})


class DatabaseConfigTestView(APIView):
	@extend_schema(tags=['Database Config'], summary='Test saved database connection', responses={200: DatabaseConfigTestResponseSerializer})
	def post(self, request, pk):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		result = DatabaseConnector(config).test_connection()
		config.last_tested_at = timezone.now()
		config.last_test_status = 'success' if result['success'] else 'failed'
		config.last_test_message = result['message']
		config.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_message'])
		return Response(result)


class DatabaseConfigTestParamsView(APIView):
	@extend_schema(tags=['Database Config'], summary='Test connection without saving', request=DatabaseConfigTestParamsSerializer, responses={200: OpenApiResponse(description='Connection test result.')})
	def post(self, request):
		serializer = DatabaseConfigTestParamsSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		config = DatabaseConfig(**serializer.validated_data, name='temporary-test')
		return Response(DatabaseConnector(config).test_connection())


class DatabaseConfigTablesView(APIView):
	@extend_schema(tags=['Database Config'], summary='List external database tables', responses={200: OpenApiResponse(description='Table names.')})
	def get(self, request, pk):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		try:
			tables = DatabaseConnector(config).list_tables()
			return Response({'success': True, 'tables': tables})
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DatabaseConfigColumnsView(APIView):
	@extend_schema(tags=['Database Config'], summary='List table columns', responses={200: OpenApiResponse(description='Column metadata.')})
	def get(self, request, pk, table_name):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		try:
			columns = DatabaseConnector(config).list_columns(table_name)
			return Response({'success': True, 'columns': columns})
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DatabaseConfigPreviewView(APIView):
	@extend_schema(tags=['Database Config'], summary='Preview table rows', responses={200: OpenApiResponse(description='Sample rows.')})
	def get(self, request, pk, table_name):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		try:
			preview = DatabaseConnector(config).preview_rows(table_name, request.query_params.get('limit', 50))
			return Response({'success': True, **preview})
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CustomerProfilePreviewView(APIView):
	@extend_schema(
		tags=['Customer Profile Config'],
		summary='Preview language lookup for MSISDNs',
		request=CustomerProfilePreviewSerializer,
		responses={200: OpenApiResponse(description='Language mapping preview')},
	)
	def post(self, request, pk):
		profile = get_object_or_404(CustomerProfileConfig, pk=pk)
		serializer = CustomerProfilePreviewSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		msisdns = serializer.validated_data['msisdns'][:100]

		try:
			connector = DatabaseConnector(profile.database_config)
			schema = connector.list_columns(profile.table_name)
			top_rows = connector.preview_rows(profile.table_name, limit=10)
			mapping = LanguageMapper(profile).lookup_batch(msisdns)
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

		rows = []
		matched = 0
		for msisdn in msisdns:
			language = mapping.get(msisdn)
			if language:
				matched += 1
			rows.append({
				'msisdn': msisdn,
				'language': language,
				'matched': bool(language),
			})

		return Response({
			'success': True,
			'data': {
				'profile_id': profile.id,
				'profile_name': profile.name,
				'total': len(msisdns),
				'matched': matched,
				'unmatched': len(msisdns) - matched,
				'default_language': profile.default_language_id,
				'rows': rows,
				'schema': schema,
				'top_rows': top_rows,
			},
		})


@extend_schema_view(
	get=extend_schema(tags=['Channel Manager'], summary='List available channels', responses={200: ChannelSerializer(many=True)}),
	post=extend_schema(tags=['Channel Manager'], summary='Create a channel', request=ChannelSerializer, responses={201: ChannelSerializer}),
)
class ChannelListCreateView(ListCreateAPIView):
	queryset = Channel.objects.all()
	serializer_class = ChannelSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		active = self.request.query_params.get('is_active')
		if active is not None and active.lower() in {'true', 'false'}:
			queryset = queryset.filter(is_active=(active.lower() == 'true'))
		return queryset


@extend_schema_view(
	get=extend_schema(tags=['Channel Manager'], summary='Get a channel', responses={200: ChannelSerializer}),
	put=extend_schema(tags=['Channel Manager'], summary='Replace a channel', request=ChannelSerializer, responses={200: ChannelSerializer}),
	patch=extend_schema(tags=['Channel Manager'], summary='Update a channel', request=ChannelSerializer, responses={200: ChannelSerializer}),
	delete=extend_schema(tags=['Channel Manager'], summary='Delete a channel', responses={204: OpenApiResponse(description='Channel deleted.')}),
)
class ChannelDetailView(RetrieveUpdateDestroyAPIView):
	queryset = Channel.objects.all()
	serializer_class = ChannelSerializer

	def destroy(self, request, *args, **kwargs):
		channel = self.get_object()
		if any(
			channel.pk in (campaign.channels_id or [])
			for campaign in Campaign.objects.only('channels_id').iterator()
		):
			return Response(
				{'detail': 'Cannot delete a channel used by a campaign.'},
				status=status.HTTP_409_CONFLICT,
			)
		channel.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
	get=extend_schema(
		tags=['Campaigns Manager'],
		summary='List all campaigns',
		parameters=[
			OpenApiParameter('status', OpenApiTypes.STR, description='Filter by campaign status.'),
			OpenApiParameter('execution_status', OpenApiTypes.STR, description='Filter by execution status.'),
			OpenApiParameter('created_by', OpenApiTypes.INT, description='Filter by creator user ID.'),
			OpenApiParameter('mine', OpenApiTypes.BOOL, description='Only campaigns created by the current user.'),
			OpenApiParameter('search', OpenApiTypes.STR, description='Search name or sender ID.'),
		],
		responses={200: CampaignListSerializer(many=True), 401: OpenApiResponse(description='Authentication required.')},
	),
	post=extend_schema(
		tags=['Campaigns Manager'],
		summary='Create a new campaign',
		request=CampaignCreateUpdateSerializer,
		responses={201: CampaignDetailSerializer, 400: OpenApiResponse(description='Validation error.')},
	),
)
class DashboardView(APIView):
	permission_classes = [IsAuthenticated]

	@extend_schema(
		tags=['Campaigns Manager'],
		summary='Get filtered campaign dashboard data',
		parameters=[
			OpenApiParameter('campaign_id', OpenApiTypes.INT),
			OpenApiParameter('status', OpenApiTypes.STR),
			OpenApiParameter('date_range', OpenApiTypes.STR),
			OpenApiParameter('date_from', OpenApiTypes.DATE),
			OpenApiParameter('date_to', OpenApiTypes.DATE),
			OpenApiParameter('page', OpenApiTypes.INT),
			OpenApiParameter('page_size', OpenApiTypes.INT),
			OpenApiParameter('sort', OpenApiTypes.STR),
		],
		responses={200: OpenApiResponse(description='Dashboard metrics and campaign page.')},
	)
	def get(self, request):
		campaigns = Campaign.objects.filter(is_deleted=False)
		if not request.user.is_superuser:
			campaigns = campaigns.filter(created_by=request.user)

		campaign_options = list(campaigns.order_by('name').values('id', 'name'))
		campaign_id = request.query_params.get('campaign_id')
		if campaign_id:
			try:
				campaign_id = int(campaign_id)
				campaigns = campaigns.filter(pk=campaign_id)
			except (TypeError, ValueError):
				return Response({'success': False, 'error': 'campaign_id must be an integer.'}, status=400)

		status_filter = request.query_params.get('status', '').strip().lower()
		allowed_statuses = {'active', 'in_progress', 'draft', 'paused', 'completed', 'cancelled', 'stopped', 'archived'}
		if status_filter and status_filter not in allowed_statuses:
			return Response({'success': False, 'error': 'Unsupported campaign status.'}, status=400)
		if status_filter == 'active':
			campaigns = campaigns.filter(status__in=['active', 'in_progress'])
		elif status_filter == 'completed':
			campaigns = campaigns.filter(status__in=['completed', 'archived'])
		elif status_filter:
			campaigns = campaigns.filter(status=status_filter)

		date_range = request.query_params.get('date_range', 'last_30_days')
		today = timezone.localdate()
		if date_range == 'today':
			date_from, date_to = today, today
		elif date_range == 'last_7_days':
			date_from, date_to = today - timedelta(days=6), today
		elif date_range == 'last_30_days':
			date_from, date_to = today - timedelta(days=29), today
		elif date_range == 'last_90_days':
			date_from, date_to = today - timedelta(days=89), today
		elif date_range == 'all_time':
			date_from = date_to = None
		elif date_range == 'custom':
			date_from = parse_date(request.query_params.get('date_from', ''))
			date_to = parse_date(request.query_params.get('date_to', ''))
			if not date_from or not date_to or date_from > date_to:
				return Response({'success': False, 'error': 'Custom date range requires valid date_from and date_to values.'}, status=400)
		else:
			return Response({'success': False, 'error': 'Unsupported date_range.'}, status=400)

		start_at = timezone.make_aware(datetime.combine(date_from, time.min)) if date_from else None
		end_at = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min)) if date_to else None

		metric_models = {
			'success_sent': (SuccessSent, 'sent_at'),
			'failed_sent': (FailedSent, 'final_attempt_at'),
			'success_delivery': (SuccessDelivery, 'delivered_at'),
			'failed_delivery': (FailedDelivery, 'failed_at'),
		}

		def history_queryset(model, timestamp_field):
			queryset = model.objects.filter(campaign_id__in=campaigns.order_by().values('id'))
			if start_at:
				queryset = queryset.filter(**{f'{timestamp_field}__gte': start_at})
			if end_at:
				queryset = queryset.filter(**{f'{timestamp_field}__lt': end_at})
			return queryset

		metric_counts = {
			key: dict(
				history_queryset(model, timestamp_field)
				.order_by()
				.values('campaign_id')
				.annotate(total=Count('id'))
				.values_list('campaign_id', 'total')
			)
			for key, (model, timestamp_field) in metric_models.items()
		}
		metrics = {key: sum(counts.values()) for key, counts in metric_counts.items()}

		status_counts = dict(
			campaigns.order_by()
			.values('status')
			.annotate(total=Count('id'))
			.values_list('status', 'total')
		)
		active_count = status_counts.get('active', 0) + status_counts.get('in_progress', 0)
		completed_count = status_counts.get('completed', 0) + status_counts.get('archived', 0)
		status_distribution = {
			'active': active_count,
			'draft': status_counts.get('draft', 0),
			'paused': status_counts.get('paused', 0),
			'completed': completed_count,
			'cancelled': status_counts.get('cancelled', 0),
		}

		sort = request.query_params.get('sort', '-updated_at')
		descending = sort.startswith('-')
		sort_key = sort[1:] if descending else sort
		sort_fields = {
			'id': 'id', 'name': 'name', 'owner': 'created_by__username',
			'type': 'schedule__schedule_type', 'schedule_type': 'schedule__schedule_type',
			'sender_id': 'sender_id', 'channels': 'channels_id', 'status': 'status',
			'execution_status': Case(
				When(status='active', then=Value('PENDING')),
				When(status='in_progress', then=Value('PROCESSING')),
				When(status='paused', then=Value('PAUSED')),
				When(status='completed', then=Value('COMPLETED')),
				When(status='stopped', then=Value('STOPPED')),
				default=Value('PENDING'), output_field=CharField(),
			),
			'target_audience': 'target_audience', 'success_sent': 'success_sent',
			'failed_sent': 'failed_sent', 'success_delivery': 'success_delivery',
			'failed_delivery': 'failed_delivery', 'updated_at': 'updated_at',
		}
		if sort_key not in sort_fields:
			sort_key = 'updated_at'

		rows = campaigns.select_related('created_by', 'schedule')
		if sort_key == 'target_audience':
			latest_audience_round = Audience.objects.filter(
				campaign_id=OuterRef('pk')
			).order_by().values('campaign_id').annotate(
				round_number=Max('round_number')
			).values('round_number')[:1]
			rows = rows.annotate(
				audience_round=Subquery(latest_audience_round),
				target_audience=Coalesce(
					Subquery(
						Audience.objects.filter(
							campaign_id=OuterRef('pk'),
							round_number=OuterRef('audience_round'),
						).order_by().values('campaign_id').annotate(
							total=Count('id')
						).values('total')[:1],
						output_field=IntegerField(),
					),
					Value(0),
					output_field=IntegerField(),
				),
			)
		elif sort_key in metric_models:
			model, timestamp_field = metric_models[sort_key]
			filtered = model.objects.filter(campaign_id=OuterRef('pk'))
			if start_at:
				filtered = filtered.filter(**{f'{timestamp_field}__gte': start_at})
			if end_at:
				filtered = filtered.filter(**{f'{timestamp_field}__lt': end_at})
			rows = rows.annotate(
				**{
					sort_key: Coalesce(
						Subquery(
							filtered.order_by().values('campaign_id').annotate(
								total=Count('id')
							).values('total')[:1],
							output_field=IntegerField(),
						),
						Value(0),
						output_field=IntegerField(),
					)
				}
			)

		ordering = sort_fields[sort_key]
		if isinstance(ordering, str):
			ordering = f'-{ordering}' if descending else ordering
		rows = rows.order_by(ordering, '-pk' if sort_key != 'id' else ordering)

		try:
			page = max(1, int(request.query_params.get('page', 1)))
			page_size = min(200, max(1, int(request.query_params.get('page_size', 50))))
		except (TypeError, ValueError):
			return Response({'success': False, 'error': 'page and page_size must be integers.'}, status=400)
		count = sum(status_counts.values())
		page_rows = list(rows[(page - 1) * page_size:page * page_size])
		page_campaign_ids = [campaign.pk for campaign in page_rows]
		channel_ids = {channel_id for campaign in page_rows for channel_id in (campaign.channels_id or [])}
		channel_names = dict(Channel.objects.filter(pk__in=channel_ids).values_list('id', 'name'))

		latest_audience_rounds = dict(
			Audience.objects.filter(campaign_id__in=page_campaign_ids)
			.order_by()
			.values('campaign_id')
			.annotate(round_number=Max('round_number'))
			.values_list('campaign_id', 'round_number')
		)
		latest_audience_filter = Q()
		for campaign_pk, round_number in latest_audience_rounds.items():
			latest_audience_filter |= Q(campaign_id=campaign_pk, round_number=round_number)
		if latest_audience_rounds:
			audience_counts = dict(
				Audience.objects.filter(latest_audience_filter)
				.order_by()
				.values('campaign_id')
				.annotate(total=Count('id'))
				.values_list('campaign_id', 'total')
			)
		else:
			audience_counts = {}

		results = [{
			'id': campaign.id,
			'name': campaign.name,
			'owner': (campaign.created_by.email or campaign.created_by.username) if campaign.created_by else '',
			'schedule_type': campaign.schedule.schedule_type if hasattr(campaign, 'schedule') else None,
			'sender_id': campaign.sender_id,
			'channels': [channel_names[channel_id] for channel_id in (campaign.channels_id or []) if channel_id in channel_names],
			'status': campaign.status,
			'execution_status': campaign.execution_status,
			'target_audience': audience_counts.get(campaign.pk, 0),
			'success_sent': metric_counts['success_sent'].get(campaign.pk, 0),
			'failed_sent': metric_counts['failed_sent'].get(campaign.pk, 0),
			'success_delivery': metric_counts['success_delivery'].get(campaign.pk, 0),
			'failed_delivery': metric_counts['failed_delivery'].get(campaign.pk, 0),
		} for campaign in page_rows]

		return Response({
			'success': True,
			'data': {
				'viewer': {
					'first_name': request.user.first_name,
					'is_superuser': request.user.is_superuser,
				},
				'kpis': {
					'total_campaigns': count,
					'active_campaigns': active_count,
					'draft_campaigns': status_counts.get('draft', 0),
					'paused_campaigns': status_counts.get('paused', 0),
					'completed_campaigns': completed_count,
				},
				'sent_vs_delivery': metrics,
				'status_distribution': status_distribution,
				'campaign_options': campaign_options,
				'campaigns': {
					'count': count,
					'page': page,
					'page_size': page_size,
					'next': page + 1 if page * page_size < count else None,
					'previous': page - 1 if page > 1 and count else None,
					'results': results,
				},
			},
		})


class CampaignListCreateView(ListCreateAPIView):
	pagination_class = StandardPagination

	def get_queryset(self):
		queryset = Campaign.objects.filter(is_deleted=False).select_related('schedule', 'audience_config').annotate(
			queue_total=_campaign_record_count(MessageObject),
			queue_processed=_campaign_record_count(
				MessageObject,
				sent_status__in=['SENT', 'SUBMITTED', 'ACCEPTED', 'REJECTED', 'FAILED'],
			),
			successful_sent=_campaign_record_count(SuccessSent),
			failed_sent=_campaign_record_count(FailedSent),
			successful_delivery=_campaign_record_count(SuccessDelivery),
			failed_delivery=_campaign_record_count(FailedDelivery),
			queue_success_sent=_campaign_record_count(
				MessageObject,
				sent_status__in=['SENT', 'SUBMITTED', 'ACCEPTED'],
			),
			queue_failed_sent=_campaign_record_count(
				MessageObject,
				sent_status__in=['REJECTED', 'FAILED'],
			),
			has_audience_members=Exists(
				AudienceMember.objects.filter(campaign_id=OuterRef('pk'), is_valid=True)
			),
		).annotate(
			total_messages=F('queue_total') + F('successful_sent') + F('failed_sent'),
			total_processed=F('queue_processed') + F('successful_sent') + F('failed_sent'),
			success_sent_count=F('successful_sent') + F('queue_success_sent'),
			failed_sent_count=F('failed_sent') + F('queue_failed_sent'),
			success_delivery_count=F('successful_delivery'),
			failed_delivery_count=F('failed_delivery'),
		)

		status_param = self.request.query_params.get('status')
		if status_param:
			queryset = queryset.filter(status=status_param)

		execution_status = self.request.query_params.get('execution_status')
		if execution_status:
			queryset = queryset.filter(execution_status=execution_status)

		created_by = self.request.query_params.get('created_by')
		if created_by:
			queryset = queryset.filter(created_by_id=created_by)

		search = self.request.query_params.get('search')
		if search:
			queryset = queryset.filter(
				Q(name__icontains=search) | Q(sender_id__icontains=search)
			)

		if self.request.query_params.get('mine', '').lower() == 'true':
			queryset = queryset.filter(created_by=self.request.user)

		return annotate_campaign_child_ids(queryset).order_by('-created_at')

	def get_serializer_context(self):
		context = super().get_serializer_context()
		if self.request.method == 'GET':
			context['channel_names_by_id'] = dict(
				Channel.objects.values_list('id', 'name')
			)
		return context

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return CampaignCreateUpdateSerializer
		return CampaignListSerializer

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		campaign = serializer.save(
			created_by=request.user if request.user.is_authenticated else None,
			status='draft',
			execution_status='PENDING',
		)
		logger.info('Campaign created: id=%s, user=%s', campaign.id, request.user.username)
		campaign_with_ids = annotate_campaign_child_ids(Campaign.objects.filter(pk=campaign.pk)).first()
		return Response(
			{
				'success': True,
				'message': 'Campaign created successfully.',
				'data': CampaignDetailSerializer(campaign_with_ids).data,
			},
			status=status.HTTP_201_CREATED,
		)


@extend_schema_view(
	get=extend_schema(
		tags=['Campaigns Manager'],
		summary='Get campaign by ID',
		responses={200: CampaignDetailSerializer, 404: OpenApiResponse(description='Campaign not found.')},
	),
	put=extend_schema(
		tags=['Campaigns Manager'],
		summary='Replace a campaign',
		request=CampaignCreateUpdateSerializer,
		responses={200: CampaignDetailSerializer, 400: OpenApiResponse(description='Campaign cannot be edited.')},
	),
	patch=extend_schema(
		tags=['Campaigns Manager'],
		summary='Update a campaign',
		request=CampaignCreateUpdateSerializer,
		responses={200: CampaignDetailSerializer, 400: OpenApiResponse(description='Campaign cannot be edited.')},
	),
	delete=extend_schema(
		tags=['Campaigns Manager'],
		summary='Soft-delete a campaign',
		responses={200: OpenApiResponse(description='Campaign deleted successfully.'), 400: OpenApiResponse(description='Campaign cannot be deleted.')},
	),
)
class CampaignDetailView(RetrieveUpdateDestroyAPIView):
	lookup_url_kwarg = 'campaign_id'

	def get_queryset(self):
		return annotate_campaign_child_ids(Campaign.objects.filter(is_deleted=False))

	def get_object(self):
		return get_object_or_404(
			annotate_campaign_child_ids(Campaign.objects.filter(is_deleted=False)),
			id=self.kwargs['campaign_id'],
			is_deleted=False,
		)

	def get_serializer_class(self):
		if self.request.method in ('PUT', 'PATCH'):
			return CampaignCreateUpdateSerializer
		return CampaignDetailSerializer

	def retrieve(self, request, *args, **kwargs):
		campaign = self.get_object()
		return Response({
			'success': True,
			'data': CampaignDetailSerializer(campaign).data,
		})

	def update(self, request, *args, **kwargs):
		partial = kwargs.pop('partial', False)
		campaign = self.get_object()
		if campaign.status != 'draft':
			return Response(
				{
					'success': False,
					'message': (
						f"Cannot edit campaign in '{campaign.status}' status. "
						'Only draft campaigns can be edited.'
					),
				},
				status=status.HTTP_400_BAD_REQUEST,
			)

		serializer = self.get_serializer(campaign, data=request.data, partial=partial)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		campaign = self.get_object()
		return Response({
			'success': True,
			'message': 'Campaign updated successfully.',
			'data': CampaignDetailSerializer(campaign).data,
		})

	def destroy(self, request, *args, **kwargs):
		campaign = self.get_object()
		campaign.soft_delete()
		return Response({
			'success': True,
			'message': 'Campaign soft-deleted successfully.',
		})


class CampaignHardDeleteView(APIView):
	"""Permanently delete a campaign from the database."""

	@extend_schema(
		tags=['Campaigns Manager'],
		summary='Permanently delete a campaign',
		responses={200: OpenApiResponse(description='Campaign permanently deleted.')},
	)
	def delete(self, request, campaign_id):
		with transaction.atomic():
			campaign = get_object_or_404(Campaign.objects.select_for_update(), id=campaign_id)
			for model in (SuccessDelivery, FailedDelivery, DeliveryRecord, SuccessSent, FailedSent, SentRecord):
				model.objects.filter(campaign=campaign).delete()
			campaign.delete()
		return Response({
			'success': True,
			'message': 'Campaign permanently deleted successfully.',
		})


@extend_schema_view(
	get=extend_schema(
		tags=['Language Manager'],
		summary='List all languages',
		responses={200: LanguageSerializer(many=True)},
	),
	post=extend_schema(
		tags=['Language Manager'],
		summary='Create a language',
		request=LanguageSerializer,
		responses={201: LanguageSerializer},
	),
)
class LanguageListCreateView(ListCreateAPIView):
	queryset = Language.objects.all()
	serializer_class = LanguageSerializer


@extend_schema_view(
	get=extend_schema(
		tags=['Language Manager'],
		summary='Get a language',
		responses={200: LanguageSerializer},
	),
	put=extend_schema(
		tags=['Language Manager'],
		summary='Replace a language',
		request=LanguageSerializer,
		responses={200: LanguageSerializer},
	),
	patch=extend_schema(
		tags=['Language Manager'],
		summary='Update a language',
		request=LanguageSerializer,
		responses={200: LanguageSerializer},
	),
	delete=extend_schema(
		tags=['Language Manager'],
		summary='Delete a language',
		responses={204: OpenApiResponse(description='Language deleted successfully.')},
	),
)
class LanguageDetailView(RetrieveUpdateDestroyAPIView):
	queryset = Language.objects.all()
	serializer_class = LanguageSerializer

	def destroy(self, request, *args, **kwargs):
		language = self.get_object()
		if MessageContent.objects.filter(
			**{language.code + '__gt': ''}
		).exists():
			return Response({
				'detail': 'Cannot delete a language that is used by message content.',
			}, status=status.HTTP_409_CONFLICT)
		language.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
	tags=['Message Content'],
	summary='List supported message languages',
	responses={200: SupportedLanguageSerializer(many=True)},
)
class MessageContentCollectionView(APIView):
	def get(self, request):
		queryset = MessageContent.objects.select_related(
			'campaign', 'default_language',
		).filter(campaign__is_deleted=False).order_by('-updated_at')
		search = request.query_params.get('search', '').strip()
		default_language = request.query_params.get('default_language')
		completeness = request.query_params.get('completeness')
		if search:
			queryset = queryset.filter(campaign__name__icontains=search)
		if default_language:
			queryset = queryset.filter(default_language__code=default_language)

		items = list(queryset)
		if completeness in {'complete', 'partial', 'empty'}:
			active_languages = list(Language.objects.filter(is_active=True).values_list('code', flat=True))
			def matches(item):
				count = sum(bool(getattr(item, code, '').strip()) for code in active_languages)
				return {
					'complete': count == len(active_languages),
					'partial': 0 < count < len(active_languages),
					'empty': count == 0,
				}[completeness]
			items = [item for item in items if matches(item)]

		paginator = StandardPagination()
		page = paginator.paginate_queryset(items, request)
		return paginator.get_paginated_response(MessageContentApiSerializer(page, many=True).data)

	def post(self, request):
		input_serializer = MessageContentApiInputSerializer(data=request.data)
		input_serializer.is_valid(raise_exception=True)
		payload = input_serializer.validated_data
		campaign = payload['campaign']
		if campaign.status != 'draft':
			return Response({'detail': f"Cannot modify message content in '{campaign.status}' status."}, status=status.HTTP_400_BAD_REQUEST)
		if MessageContent.objects.filter(campaign=campaign).exists():
			return Response({'detail': 'Message content already exists for this campaign.'}, status=status.HTTP_409_CONFLICT)
		write_data = dict(payload['content'])
		write_data['default_language'] = payload['default_language'].pk
		content_serializer = MessageContentCreateUpdateSerializer(data=write_data)
		content_serializer.is_valid(raise_exception=True)
		content = content_serializer.save(campaign=campaign)
		return Response(MessageContentApiSerializer(content).data, status=status.HTTP_201_CREATED)


class MessageContentResourceView(APIView):
	def get_object(self, pk):
		return get_object_or_404(
			MessageContent.objects.select_related('campaign', 'default_language'),
			pk=pk,
			campaign__is_deleted=False,
		)

	def get(self, request, pk):
		return Response(MessageContentApiSerializer(self.get_object(pk)).data)

	def _update(self, request, pk, partial):
		content = self.get_object(pk)
		if content.campaign.status != 'draft':
			return Response({'detail': f"Cannot modify message content in '{content.campaign.status}' status."}, status=status.HTTP_400_BAD_REQUEST)
		input_serializer = MessageContentApiInputSerializer(
			data=request.data, partial=partial,
		)
		input_serializer.is_valid(raise_exception=True)
		payload = input_serializer.validated_data
		campaign = payload.get('campaign', content.campaign)
		if campaign.status != 'draft':
			return Response({'detail': f"Cannot modify message content in '{campaign.status}' status."}, status=status.HTTP_400_BAD_REQUEST)
		if campaign.pk != content.campaign_id and MessageContent.objects.filter(campaign=campaign).exists():
			return Response({'detail': 'Message content already exists for this campaign.'}, status=status.HTTP_409_CONFLICT)
		write_data = dict(payload.get('content', {}))
		if 'default_language' in payload:
			write_data['default_language'] = payload['default_language'].pk
		content_serializer = MessageContentCreateUpdateSerializer(
			content, data=write_data, partial=partial,
		)
		content_serializer.is_valid(raise_exception=True)
		with transaction.atomic():
			content_serializer.save()
			if campaign.pk != content.campaign_id:
				content.campaign = campaign
				content.save(update_fields=['campaign', 'updated_at'])
		return Response(MessageContentApiSerializer(self.get_object(content.pk)).data)

	def put(self, request, pk):
		return self._update(request, pk, partial=False)

	def patch(self, request, pk):
		return self._update(request, pk, partial=True)

	def delete(self, request, pk):
		content = self.get_object(pk)
		if content.campaign.status != 'draft':
			return Response({'detail': f"Cannot modify message content in '{content.campaign.status}' status."}, status=status.HTTP_400_BAD_REQUEST)
		content.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


class MessageLanguageListView(APIView):
	def get(self, request):
		return Response({
			'success': True,
			'data': [
				{'code': language.code, 'name': language.name}
				for language in Language.objects.filter(is_active=True)
			],
		})


class MessageContentDetailView(APIView):
	"""Create and manage one message-content record per campaign."""

	def _get_campaign(self, campaign_id):
		return get_object_or_404(Campaign, id=campaign_id, is_deleted=False)

	def _editable_error(self, campaign):
		if campaign.status != 'draft':
			return Response({
				'success': False,
				'message': (
					f"Cannot modify message content in '{campaign.status}' status. "
					'Only draft campaigns can be edited.'
				),
			}, status=status.HTTP_400_BAD_REQUEST)
		return None

	def _get_content(self, campaign):
		return get_object_or_404(MessageContent, campaign=campaign)

	@extend_schema(
		tags=['Message Content'],
		summary='Get message content for a campaign',
		responses={200: MessageContentSerializer},
	)
	def get(self, request, campaign_id):
		campaign = self._get_campaign(campaign_id)
		content = self._get_content(campaign)
		return Response({'success': True, 'data': MessageContentSerializer(content).data})

	@extend_schema(
		tags=['Message Content'],
		summary='Add message content to a campaign',
		request=MessageContentCreateUpdateSerializer,
		responses={201: MessageContentSerializer},
	)
	def post(self, request, campaign_id):
		campaign = self._get_campaign(campaign_id)
		if error := self._editable_error(campaign):
			return error
		if MessageContent.objects.filter(campaign=campaign).exists():
			return Response({
				'success': False,
				'message': 'Message content already exists. Use PUT or PATCH to update it.',
			}, status=status.HTTP_409_CONFLICT)
		serializer = MessageContentCreateUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		content = serializer.save(campaign=campaign)
		return Response({
			'success': True,
			'message': 'Message content added successfully.',
			'data': MessageContentSerializer(content).data,
		}, status=status.HTTP_201_CREATED)

	def _update(self, request, campaign_id, partial):
		campaign = self._get_campaign(campaign_id)
		if error := self._editable_error(campaign):
			return error
		content = self._get_content(campaign)
		serializer = MessageContentCreateUpdateSerializer(
			content, data=request.data, partial=partial,
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response({
			'success': True,
			'message': 'Message content updated successfully.',
			'data': MessageContentSerializer(content).data,
		})

	@extend_schema(
		tags=['Message Content'],
		summary='Replace message content',
		request=MessageContentCreateUpdateSerializer,
		responses={200: MessageContentSerializer},
	)
	def put(self, request, campaign_id):
		return self._update(request, campaign_id, partial=False)

	@extend_schema(
		tags=['Message Content'],
		summary='Partially update message content',
		request=MessageContentCreateUpdateSerializer,
		responses={200: MessageContentSerializer},
	)
	def patch(self, request, campaign_id):
		return self._update(request, campaign_id, partial=True)

	@extend_schema(
		tags=['Message Content'],
		summary='Delete message content',
		responses={200: OpenApiResponse(description='Message content deleted.')},
	)
	def delete(self, request, campaign_id):
		campaign = self._get_campaign(campaign_id)
		if error := self._editable_error(campaign):
			return error
		content = self._get_content(campaign)
		content.delete()
		return Response({
			'success': True,
			'message': 'Message content deleted successfully.',
		})


class ScheduleDetailView(APIView):
	"""Manage the one schedule belonging to a campaign."""

	def _campaign(self, campaign_id):
		return get_object_or_404(Campaign, id=campaign_id, is_deleted=False)

	def _editable_error(self, campaign):
		if campaign.status != 'draft':
			return Response({
				'success': False,
				'message': f"Cannot modify schedule in '{campaign.status}' status.",
			}, status=status.HTTP_400_BAD_REQUEST)
		return None

	def _schedule(self, campaign):
		return get_object_or_404(Schedule, campaign=campaign)

	@extend_schema(
		tags=['Schedule Management'],
		summary='Get campaign schedule',
		responses={200: ScheduleSerializer},
	)
	def get(self, request, campaign_id):
		campaign = self._campaign(campaign_id)
		schedule = self._schedule(campaign)
		return Response({'success': True, 'data': ScheduleSerializer(schedule).data})

	@extend_schema(
		tags=['Schedule Management'],
		summary='Create campaign schedule',
		request=ScheduleCreateUpdateSerializer,
		responses={201: ScheduleSerializer, 409: OpenApiResponse(description='Schedule already exists.')},
	)
	def post(self, request, campaign_id):
		campaign = self._campaign(campaign_id)
		if error := self._editable_error(campaign):
			return error
		if Schedule.objects.filter(campaign=campaign).exists():
			return Response({'success': False, 'message': 'A schedule already exists. Use PUT or PATCH.'}, status=status.HTTP_409_CONFLICT)
		serializer = ScheduleCreateUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		schedule = serializer.save(campaign=campaign)
		return Response({'success': True, 'message': 'Schedule added successfully.', 'data': ScheduleSerializer(schedule).data}, status=status.HTTP_201_CREATED)

	def _update(self, request, campaign_id, partial):
		campaign = self._campaign(campaign_id)
		if error := self._editable_error(campaign):
			return error
		schedule = self._schedule(campaign)
		serializer = ScheduleCreateUpdateSerializer(schedule, data=request.data, partial=partial)
		serializer.is_valid(raise_exception=True)
		schedule = serializer.save()
		return Response({'success': True, 'message': 'Schedule updated successfully.', 'data': ScheduleSerializer(schedule).data})

	@extend_schema(tags=['Schedule Management'], summary='Replace campaign schedule', request=ScheduleCreateUpdateSerializer, responses={200: ScheduleSerializer})
	def put(self, request, campaign_id):
		return self._update(request, campaign_id, partial=False)

	@extend_schema(tags=['Schedule Management'], summary='Partially update campaign schedule', request=ScheduleCreateUpdateSerializer, responses={200: ScheduleSerializer})
	def patch(self, request, campaign_id):
		return self._update(request, campaign_id, partial=True)

	@extend_schema(tags=['Schedule Management'], summary='Delete campaign schedule', responses={200: OpenApiResponse(description='Schedule deleted.')})
	def delete(self, request, campaign_id):
		campaign = self._campaign(campaign_id)
		if error := self._editable_error(campaign):
			return error
		schedule = self._schedule(campaign)
		schedule.delete()
		return Response({'success': True, 'message': 'Schedule deleted successfully.'})


def _schedule_window_is_open(schedule, now=None):
	from datetime import time as time_value
	from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

	now = now or timezone.now()
	try:
		local_now = timezone.localtime(now, ZoneInfo(schedule.timezone))
	except (ZoneInfoNotFoundError, ValueError):
		logger.exception('Invalid schedule timezone schedule_id=%s timezone=%s', schedule.pk, schedule.timezone)
		return False, None

	local_date = local_now.date()
	if not schedule.is_active or schedule.schedule_status != 'active':
		return False, local_date
	if local_date < schedule.start_date or (schedule.end_date and local_date > schedule.end_date):
		return False, local_date
	if schedule.schedule_type == 'once' and local_date != schedule.start_date:
		return False, local_date
	if schedule.schedule_type == 'weekly' and local_date.weekday() not in (schedule.run_days or []):
		return False, local_date
	if schedule.schedule_type == 'monthly' and local_date.day != schedule.start_date.day:
		return False, local_date

	for window in schedule.time_windows or []:
		try:
			start = time_value.fromisoformat(window['start'])
			end = time_value.fromisoformat(window['end'])
		except (KeyError, TypeError, ValueError):
			logger.warning('Invalid time window schedule_id=%s window=%r', schedule.pk, window)
			continue
		if start <= local_now.time().replace(tzinfo=None) < end:
			return True, local_date
	return False, local_date


def _scheduler_round_number(schedule, campaign, audience_config, should_run, local_date):
	from zoneinfo import ZoneInfo

	latest_message_build = MessageBuildJob.objects.filter(campaign=campaign).order_by('-created_at').first()
	latest_message = MessageObject.objects.filter(campaign=campaign).aggregate(
		latest_round=Max('round_number'),
		latest_built_at=Max('built_at'),
	)
	round_candidates = [schedule.current_round, latest_message['latest_round'] or 0]
	if latest_message_build:
		round_candidates.append(latest_message_build.round_number)
	if audience_config:
		round_candidates.append(audience_config.last_rebuild_round)
	current_round = max(round_candidates)
	if current_round < 1:
		return 1
	if not should_run:
		return current_round

	latest_build = MessageBuildJob.objects.filter(
		campaign=campaign,
		round_number=current_round,
	).order_by('-created_at').first()
	build_at = latest_build.created_at if latest_build else None
	if latest_message['latest_round'] == current_round:
		build_at = max(filter(None, (build_at, latest_message['latest_built_at'])), default=None)
	if audience_config and audience_config.last_rebuild_round == current_round:
		build_at = max(filter(None, (build_at, audience_config.last_rebuild_completed_at)), default=None)
	if build_at and timezone.localtime(build_at, timezone=ZoneInfo(schedule.timezone)).date() == local_date:
		return current_round
	return current_round + 1


class ScheduleDueNowView(APIView):
	@extend_schema(tags=['Schedule Management'], summary='List campaign schedules due now')
	def get(self, request):
		rows = []
		schedules = Schedule.objects.filter(
			is_active=True,
			campaign__is_deleted=False,
	).select_related('campaign', 'campaign__audience_config').order_by('campaign_id')
		for schedule in schedules:
			campaign = schedule.campaign
			should_run, local_date = _schedule_window_is_open(schedule)
			try:
				audience_config = campaign.audience_config
			except AudienceConfig.DoesNotExist:
				audience_config = None
			round_number = _scheduler_round_number(
				schedule, campaign, audience_config, should_run, local_date,
			)
			active_build = audience_config and AudienceBuildJob.objects.filter(
				audience_config=audience_config,
				status__in=['PENDING', 'RUNNING'],
			).exists()
			audience_exists = AudienceMember.objects.filter(
				campaign=campaign,
				round_number=round_number,
				is_valid=True,
			).exists()
			batch_id = f'campaign-{campaign.id}-round-{round_number}'
			reusable_audience_exists = audience_exists or AudienceMember.objects.filter(
				campaign=campaign,
				round_number__lt=round_number,
				is_valid=True,
			).exists()
			rows.append({
				'campaign_id': campaign.id,
				'round_number': round_number,
				'should_run': should_run,
				'is_ready': campaign.is_ready_to_execute,
				'audience_needs_rebuild': bool(
					audience_config
					and audience_config.rebuild_on_each_round
					and audience_config.last_rebuild_round < round_number
					and not active_build
				),
				'messages_need_build': bool(
					reusable_audience_exists
					and not MessageObject.objects.filter(campaign=campaign, batch_id=batch_id).exists()
				),
				'audience_config_id': audience_config.id if audience_config else None,
			})
		return Response({'success': True, 'data': rows})


class ScheduleCollectionView(APIView):
	@extend_schema(tags=['Schedule Management'], summary='List schedules')
	def get(self, request):
		qs = Schedule.objects.select_related('campaign').all()
		if schedule_type := request.query_params.get('schedule_type'):
			qs = qs.filter(schedule_type=schedule_type)
		if campaign_status := request.query_params.get('campaign_status'):
			qs = qs.filter(campaign__status=campaign_status)
		if is_active := request.query_params.get('is_active'):
			qs = qs.filter(is_active=is_active.lower() == 'true')
		paginator = StandardPagination()
		page = paginator.paginate_queryset(qs, request)
		return paginator.get_paginated_response(ScheduleSerializer(page, many=True).data)

	@extend_schema(tags=['Schedule Management'], summary='Create a schedule')
	def post(self, request):
		campaign = get_object_or_404(Campaign, pk=request.data.get('campaign'), is_deleted=False)
		if campaign.status != 'draft':
			return Response({'success': False, 'message': 'Only draft campaigns can be scheduled.'}, status=status.HTTP_400_BAD_REQUEST)
		if Schedule.objects.filter(campaign=campaign).exists():
			return Response({'success': False, 'message': 'A schedule already exists for this campaign.'}, status=status.HTTP_409_CONFLICT)
		serializer = ScheduleCreateUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		schedule = serializer.save(campaign=campaign)
		return Response({'success': True, 'data': ScheduleSerializer(schedule).data}, status=status.HTTP_201_CREATED)


class ScheduleSummaryView(APIView):
	@extend_schema(tags=['Schedule Management'], summary='Summarize schedules')
	def get(self, request):
		qs = Schedule.objects.all()
		by_type = {row['schedule_type']: row['count'] for row in qs.values('schedule_type').annotate(count=Count('id'))}
		by_status = {row['schedule_status']: row['count'] for row in qs.values('schedule_status').annotate(count=Count('id'))}
		return Response({
			'total_schedules': qs.count(),
			'by_type': by_type,
			'by_status': by_status,
			'by_window_status': by_status,
			'active_schedules': qs.filter(is_active=True).count(),
			'inactive_schedules': qs.filter(is_active=False).count(),
			'running_today': qs.filter(is_active=True, next_run_date=timezone.localdate()).count(),
		})


class ScheduleResourceView(APIView):
	def _schedule(self, pk):
		return get_object_or_404(Schedule.objects.select_related('campaign'), pk=pk)

	@extend_schema(tags=['Schedule Management'], summary='Get schedule details')
	def get(self, request, pk):
		return Response({'success': True, 'data': ScheduleSerializer(self._schedule(pk)).data})

	@extend_schema(tags=['Schedule Management'], summary='Update a schedule')
	def patch(self, request, pk):
		schedule = self._schedule(pk)
		if schedule.campaign.status != 'draft':
			return Response({'success': False, 'message': 'Only draft campaign schedules can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
		serializer = ScheduleCreateUpdateSerializer(schedule, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		schedule = serializer.save()
		return Response({'success': True, 'data': ScheduleSerializer(schedule).data})

	@extend_schema(tags=['Schedule Management'], summary='Delete a schedule')
	def delete(self, request, pk):
		schedule = self._schedule(pk)
		if schedule.campaign.status != 'draft':
			return Response({'success': False, 'message': 'Only draft campaign schedules can be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
		schedule.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


class ScheduleUpcomingWindowsView(APIView):
	@extend_schema(tags=['Schedule Management'], summary='Get upcoming schedule windows')
	def get(self, request, pk):
		schedule = get_object_or_404(Schedule, pk=pk)
		return ScheduleUpcomingView().get(request, schedule.campaign_id)


class ScheduleActivationView(APIView):
	def post(self, request, pk):
		schedule = get_object_or_404(Schedule, pk=pk)
		schedule.is_active = True
		if schedule.schedule_status == 'paused':
			schedule.schedule_status = 'active'
		schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
		return Response({'detail': 'Schedule activated.', 'is_active': True})


class ScheduleDeactivationView(APIView):
	def post(self, request, pk):
		schedule = get_object_or_404(Schedule, pk=pk)
		schedule.is_active = False
		schedule.schedule_status = 'paused'
		schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
		return Response({'detail': 'Schedule deactivated.', 'is_active': False})


class ScheduleResetView(APIView):
	def post(self, request, pk):
		schedule = get_object_or_404(Schedule, pk=pk)
		schedule.current_round = 0
		schedule.completed_windows = []
		schedule.total_windows_completed = 0
		schedule.last_processed_at = None
		schedule.next_run_date = schedule.start_date
		schedule.is_active = True
		schedule.schedule_status = 'active'
		schedule.save(update_fields=[
			'current_round', 'completed_windows', 'total_windows_completed',
			'last_processed_at', 'next_run_date', 'is_active', 'schedule_status', 'updated_at',
		])
		return Response({'success': True, 'data': ScheduleSerializer(schedule).data})


class CampaignBuildMessagesView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='Build MessageObject rows for a campaign', responses={201: OpenApiResponse(description='Build result.')})
	def post(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		try:
			round_number = int(request.data.get('round_number', 1))
		except (TypeError, ValueError):
			return Response({'success': False, 'message': 'round_number must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
		if round_number < 1:
			return Response({'success': False, 'message': 'round_number must be at least 1.'}, status=status.HTTP_400_BAD_REQUEST)
		batch_id = request.data.get('batch_id') or f'campaign-{campaign.id}-round-{round_number}'
		if not isinstance(batch_id, str) or len(batch_id) > 50:
			return Response({'success': False, 'message': 'batch_id must be a string of at most 50 characters.'}, status=status.HTTP_400_BAD_REQUEST)
		try:
			result = MessageBuilder(campaign=campaign, round_number=round_number, batch_id=batch_id).build()
			result['is_ready_to_execute'] = (
				campaign.refresh_readiness_flag()
				if campaign.status == 'draft'
				else campaign.is_ready_to_execute
			)
		except ValueError as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
		except Exception as exc:
			return Response({'success': False, 'message': f'Build failed: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
		return Response({'success': True, 'message': 'Messages built successfully.', 'data': result}, status=status.HTTP_201_CREATED)


class CampaignMessageBuildProgressView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='Get latest message-object build progress', responses={200: OpenApiResponse(description='Message build progress.')})
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		job = campaign.message_build_jobs.order_by('-created_at').first()
		if job is None:
			return Response({'success': True, 'data': None})
		return Response({'success': True, 'data': {
			'id': job.id,
			'campaign_id': campaign.id,
			'batch_id': job.batch_id,
			'round_number': job.round_number,
			'status': job.status,
			'phase': job.phase,
			'processed': job.processed_rows,
			'total': job.total_rows,
			'built': job.built_rows,
			'skipped': job.skipped_rows,
			'failed': job.failed_rows,
			'percent': job.percent,
			'error': job.error_message or None,
			'started_at': job.started_at,
			'completed_at': job.completed_at,
		}})


class CampaignMessagesListView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='List MessageObject rows for a campaign', responses={200: OpenApiResponse(description='Message list.')})
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		qs = MessageObject.objects.filter(campaign=campaign).order_by('id').select_related('language', 'channel')
		status_filter = request.query_params.get('status')
		if status_filter:
			qs = qs.filter(sent_status=status_filter)
		paginator = StandardPagination()
		page = paginator.paginate_queryset(qs, request)
		data = [
			{
				'id': m.id,
				'message_id': m.message_id,
				'recipient': m.recipient,
				'sender_id': m.sender_id,
				'language_code': m.language.code if m.language else None,
				'message_content': m.message_content,
				'message_parts': MessageBuilder._calculate_parts(m.message_content),
				'status': m.sent_status,
				'batch_id': m.batch_id,
				'built_at': m.built_at,
			}
			for m in page
		]
		return paginator.get_paginated_response(data)


class CampaignMessagesStatsView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='Get MessageObject build stats for a campaign', responses={200: OpenApiResponse(description='Stats payload.')})
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		qs = MessageObject.objects.filter(campaign=campaign).select_related('language')
		agg = qs.aggregate(
			total=Count('id'),
			pending=Count('id', filter=Q(sent_status='PENDING')),
			processing=Count('id', filter=Q(sent_status='PROCESSING')),
		)
		lang_breakdown = dict(
			qs.values_list('language__code').annotate(c=Count('id')).values_list('language__code', 'c')
		)
		return Response({
			'success': True,
			'data': {
				'campaign_id': campaign.id,
				'total': agg['total'] or 0,
				'pending': agg['pending'] or 0,
				'processing': agg['processing'] or 0,
				'language_breakdown': lang_breakdown,
			},
		})


def _campaign_message_batches(messages, campaign_id=None):
	batch_rows = messages.exclude(batch_id='').values('batch_id').annotate(
		total_messages=Count('id'),
		success_count=Count('id', filter=Q(sent_status__in=['SENT', 'SUBMITTED', 'ACCEPTED'])),
		failed_count=Count('id', filter=Q(sent_status__in=['REJECTED', 'FAILED'])),
		pending_count=Count('id', filter=Q(sent_status='PENDING')),
		created_at=Min('built_at'),
	)
	result_by_id = {row['batch_id']: row for row in batch_rows}

	if campaign_id is not None:
		for model, count_key in (
			(SuccessSent, 'success_count'),
			(FailedSent, 'failed_count'),
		):
			rows = model.objects.filter(campaign_id=campaign_id).exclude(batch_id='').values('batch_id').annotate(
				count=Count('id'),
				created_at=Min('created_at'),
			)
			for row in rows:
				batch = result_by_id.setdefault(row['batch_id'], {
					'batch_id': row['batch_id'],
					'total_messages': 0,
					'success_count': 0,
					'failed_count': 0,
					'pending_count': 0,
					'delivered_count': 0,
					'failed_delivery_count': 0,
					'created_at': row['created_at'],
				})
				batch[count_key] = batch.get(count_key, 0) + row['count']
				batch['total_messages'] += row['count']
				if batch['created_at'] is None or row['created_at'] < batch['created_at']:
					batch['created_at'] = row['created_at']

	result = []
	for batch in result_by_id.values():
		if batch['pending_count']:
			batch_status = 'PROCESSING' if batch['success_count'] or batch['failed_count'] else 'PENDING'
		else:
			batch_status = 'FAILED' if batch['failed_count'] else 'COMPLETED'
		result.append({**batch, 'status': batch_status})
	return sorted(result, key=lambda row: row['created_at'] or timezone.now(), reverse=True)


class CampaignProgressView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='Get campaign message delivery progress', responses={200: OpenApiResponse(description='Campaign progress and batch summary.')})
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		messages = MessageObject.objects.filter(campaign=campaign)
		queue_counts = messages.aggregate(
			total=Count('id'),
			sent=Count('id', filter=Q(sent_status__in=['SENT', 'SUBMITTED', 'ACCEPTED'])),
			failed=Count('id', filter=Q(sent_status__in=['REJECTED', 'FAILED'])),
			pending=Count('id', filter=Q(sent_status='PENDING')),
			processed=Count('id', filter=Q(sent_status__in=['SENT', 'SUBMITTED', 'ACCEPTED', 'REJECTED', 'FAILED'])),
		)
		successful_sent = SuccessSent.objects.filter(campaign=campaign).count()
		failed_sent = FailedSent.objects.filter(campaign=campaign).count()
		successful_delivery = SuccessDelivery.objects.filter(campaign=campaign).count()
		failed_delivery = FailedDelivery.objects.filter(campaign=campaign).count()
		total = (queue_counts['total'] or 0) + successful_sent + failed_sent
		sent = (queue_counts['sent'] or 0) + successful_sent
		failed = (queue_counts['failed'] or 0) + failed_sent
		delivered = successful_delivery
		failed_delivery_total = failed_delivery
		processed = (queue_counts['processed'] or 0) + successful_sent + failed_sent
		batches = _campaign_message_batches(messages, campaign_id=campaign.pk)
		batch_counts = {
			'total_batches': len(batches),
			'completed_batches': sum(batch['status'] == 'COMPLETED' for batch in batches),
			'failed_batches': sum(batch['status'] == 'FAILED' for batch in batches),
			'in_progress_batches': sum(batch['status'] in {'PENDING', 'PROCESSING'} for batch in batches),
		}
		return Response({
			'campaign_id': campaign.pk,
			'campaign_name': campaign.name,
			'progress': {
				'total_messages': total,
				'sent_count': sent,
				'delivered_count': delivered,
				'failed_count': failed,
				'failed_delivery_count': failed_delivery_total,
				'pending_count': queue_counts['pending'] or 0,
				'progress_percent': round(processed / total * 100, 2) if total else 0,
				'status': campaign.status,
			},
			'batches': batch_counts,
			'recent_batches': batches[:10],
		})


class CampaignMessagesBatchesView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='List campaign message batches', responses={200: OpenApiResponse(description='Campaign message batches.')})
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		batches = _campaign_message_batches(MessageObject.objects.filter(campaign=campaign), campaign_id=campaign.pk)
		status_filter = request.query_params.get('status')
		if status_filter:
			batches = [batch for batch in batches if batch['status'] == status_filter.upper()]
		return Response({'results': batches})


class CampaignMessagesClearView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='Clear MessageObject rows for a campaign', responses={200: OpenApiResponse(description='Clear result.')})
	def delete(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		deleted, _ = MessageObject.objects.filter(campaign=campaign).delete()
		return Response({'success': True, 'message': f'Cleared {deleted} messages.'})


class ScheduleUpcomingView(APIView):
	@extend_schema(
		tags=['Schedule Management'],
		summary='Get upcoming schedule windows',
		parameters=[OpenApiParameter('limit', OpenApiTypes.INT, description='Maximum windows to return, 1-50.')],
		responses={200: OpenApiResponse(description='Upcoming schedule windows.')},
	)
	def get(self, request, campaign_id):
		from calendar import monthrange
		from datetime import date, timedelta

		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		schedule = get_object_or_404(Schedule, campaign=campaign)
		try:
			limit = max(1, min(int(request.query_params.get('limit', 10)), 50))
		except (TypeError, ValueError):
			limit = 10
		results = []
		current = max(date.today(), schedule.start_date)

		if schedule.schedule_type == 'once':
			if not schedule.end_date or schedule.start_date <= schedule.end_date:
				results.append(schedule.start_date)
		elif schedule.schedule_type in ('daily', 'weekly'):
			while len(results) < limit and (not schedule.end_date or current <= schedule.end_date):
				if schedule.schedule_type == 'daily' or current.weekday() in schedule.run_days:
					results.append(current)
				current += timedelta(days=1)
		else:
			while len(results) < limit:
				if schedule.end_date and current > schedule.end_date:
					break
				if current.day == schedule.start_date.day:
					results.append(current)
				next_month = current.month % 12 + 1
				next_year = current.year + (current.month // 12)
				current = current.replace(
					year=next_year,
					month=next_month,
					day=min(schedule.start_date.day, monthrange(next_year, next_month)[1]),
				)

		return Response({
			'success': True,
			'schedule_type': schedule.schedule_type,
			'schedule_summary': schedule.get_schedule_summary(),
			'upcoming_windows': [
				{'date': run_date.isoformat(), 'day': run_date.strftime('%A'), 'windows': schedule.time_windows}
				for run_date in results
			],
		})
