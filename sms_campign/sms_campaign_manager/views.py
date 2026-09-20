"""API views for Campaign Manager."""

import logging
import os

from django.db.models import Count, Q, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view

from .constants import SUPPORTED_LANGUAGES
from .models import (
	AudienceConfig,
	AudienceMember,
	Campaign,
	Channel,
	CustomerProfileConfig,
	DatabaseConfig,
	DeliveryRecord,
	Language,
	MessageContent,
	MessageObject,
	Schedule,
	SentRecord,
	SenderID,
	SMSCConfig,
	EmailServerConfig,
	EmailCampaignReport,
)
from .pagination import StandardPagination
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
	LanguageSerializer,
	MessageContentCreateUpdateSerializer,
	MessageContentSerializer,
	SupportedLanguageSerializer,
	ScheduleCreateUpdateSerializer,
	ScheduleSerializer,
	SenderIDSerializer,
	SenderIDCreateUpdateSerializer,
	SMSCConfigSerializer,
	SMSCConfigCreateUpdateSerializer,
	EmailServerConfigSerializer,
	EmailCampaignReportSerializer,
)
from .services.database_connector import DatabaseConnector
from .services.language_mapper import LanguageMapper
from .services.delivery_tracker_service import DeliveryTrackerService
from .services.campaign_actions import CampaignActionsService
from .services.campaign_readiness import CampaignReadinessService
from .services.audience_service import AudienceService, AudienceBuildService
from .services.sent_tracker_service import SentTrackerService
from .services.message_builder import MessageBuilder
from .kafka import enqueue_event, TOPIC_DLR
from django.conf import settings

logger = logging.getLogger(__name__)


def annotate_campaign_child_ids(queryset):
    return queryset.annotate(
        audience_id=Subquery(
            AudienceMember.objects.filter(campaign_id=OuterRef('pk')).values('id')[:1],
        ),
        message_content_id=Subquery(
            MessageContent.objects.filter(campaign_id=OuterRef('pk')).values('id')[:1],
        ),
        schedule_id=Subquery(
            Schedule.objects.filter(campaign_id=OuterRef('pk')).values('id')[:1],
        ),
    )


class SenderIDListCreateView(ListCreateAPIView):
	queryset = SenderID.objects.all()
	serializer_class = SenderIDSerializer

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


@extend_schema_view(
	get=extend_schema(
		tags=['Email Server Config'],
		summary='List email servers',
		responses={200: EmailServerConfigSerializer(many=True)},
	),
	post=extend_schema(
		tags=['Email Server Config'],
		summary='Create email server',
		request=EmailServerConfigSerializer,
		responses={201: EmailServerConfigSerializer},
	),
)
class EmailServerConfigListCreateView(ListCreateAPIView):
	queryset = EmailServerConfig.objects.all()
	serializer_class = EmailServerConfigSerializer


@extend_schema_view(
	get=extend_schema(
		tags=['Email Server Config'],
		summary='Get email server',
		responses={200: EmailServerConfigSerializer},
	),
	put=extend_schema(
		tags=['Email Server Config'],
		summary='Replace email server',
		request=EmailServerConfigSerializer,
		responses={200: EmailServerConfigSerializer},
	),
	patch=extend_schema(
		tags=['Email Server Config'],
		summary='Update email server',
		request=EmailServerConfigSerializer,
		responses={200: EmailServerConfigSerializer},
	),
	delete=extend_schema(
		tags=['Email Server Config'],
		summary='Delete email server',
		responses={204: OpenApiResponse(description='Email server deleted.')},
	),
)
class EmailServerConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = EmailServerConfig.objects.all()
	serializer_class = EmailServerConfigSerializer


@extend_schema_view(
	get=extend_schema(
		tags=['Email Campaign Reports'],
		summary='List campaign reports',
		responses={200: EmailCampaignReportSerializer(many=True)},
	),
	post=extend_schema(
		tags=['Email Campaign Reports'],
		summary='Create campaign report',
		request=EmailCampaignReportSerializer,
		responses={201: EmailCampaignReportSerializer},
	),
)
class EmailCampaignReportListCreateView(ListCreateAPIView):
	serializer_class = EmailCampaignReportSerializer

	def get_queryset(self):
		return EmailCampaignReport.objects.filter(owner=self.request.user).prefetch_related('recipients', 'campaigns')


@extend_schema_view(
	get=extend_schema(
		tags=['Email Campaign Reports'],
		summary='Get campaign report',
		responses={200: EmailCampaignReportSerializer},
	),
	put=extend_schema(
		tags=['Email Campaign Reports'],
		summary='Replace campaign report',
		request=EmailCampaignReportSerializer,
		responses={200: EmailCampaignReportSerializer},
	),
	patch=extend_schema(
		tags=['Email Campaign Reports'],
		summary='Update campaign report',
		request=EmailCampaignReportSerializer,
		responses={200: EmailCampaignReportSerializer},
	),
	delete=extend_schema(
		tags=['Email Campaign Reports'],
		summary='Delete campaign report',
		responses={204: OpenApiResponse(description='Campaign report deleted.')},
	),
)
class EmailCampaignReportDetailView(RetrieveUpdateDestroyAPIView):
	serializer_class = EmailCampaignReportSerializer

	def get_queryset(self):
		return EmailCampaignReport.objects.filter(owner=self.request.user).prefetch_related('recipients', 'campaigns')


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
	@extend_schema(tags=['Databases'], summary='List customer profile configurations', responses={200: CustomerProfileConfigSerializer(many=True)})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Databases'], summary='Create customer profile configuration', request=CustomerProfileConfigSerializer, responses={201: CustomerProfileConfigSerializer})
	def post(self, request, *args, **kwargs):
		return super().post(request, *args, **kwargs)


class CustomerProfileConfigDetailView(RetrieveUpdateDestroyAPIView):
	queryset = CustomerProfileConfig.objects.all()
	serializer_class = CustomerProfileConfigSerializer

	@extend_schema(tags=['Databases'], summary='Get customer profile configuration', responses={200: CustomerProfileConfigSerializer})
	def get(self, request, *args, **kwargs):
		return super().get(request, *args, **kwargs)

	@extend_schema(tags=['Databases'], summary='Replace customer profile configuration', request=CustomerProfileConfigSerializer, responses={200: CustomerProfileConfigSerializer})
	def put(self, request, *args, **kwargs):
		return super().put(request, *args, **kwargs)

	@extend_schema(tags=['Databases'], summary='Update customer profile configuration', request=CustomerProfileConfigSerializer, responses={200: CustomerProfileConfigSerializer})
	def patch(self, request, *args, **kwargs):
		return super().patch(request, *args, **kwargs)

	@extend_schema(tags=['Databases'], summary='Delete customer profile configuration', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, *args, **kwargs):
		return super().delete(request, *args, **kwargs)


class CampaignAudienceView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get campaign audience summary', responses={200: OpenApiResponse(description='Campaign audience summary.')})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		return Response({'success': True, 'data': {
			'campaign_id': campaign.id,
			'default_language': campaign.default_language,
			'source_type': campaign.source_type,
			'source_config': campaign.source_config,
			'main_database': campaign.main_database_id,
			'main_table': campaign.main_table,
			'main_msisdn_column': campaign.main_msisdn_column,
			'main_language_column': campaign.main_language_column,
			'file_path': campaign.file_path,
			'file_msisdn_column': campaign.file_msisdn_column,
			'file_language_column': campaign.file_language_column,
			'customer_profile': campaign.customer_profile_id,
			'total_count': campaign.total_count,
			'valid_count': campaign.valid_count,
			'invalid_count': campaign.invalid_count,
			'language_matched': campaign.language_matched,
			'language_defaulted': campaign.language_defaulted,
			'is_processed': campaign.is_processed,
			'processing_started_at': campaign.processing_started_at,
			'processing_completed_at': campaign.processing_completed_at,
		}})

	@extend_schema(tags=['Audience Management'], summary='Add manual campaign audience', request=ManualAudienceInputSerializer, responses={201: OpenApiResponse(description='Campaign audience summary.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		serializer = ManualAudienceInputSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		profile = None
		profile_id = serializer.validated_data.get('customer_profile_id')
		if profile_id:
			profile = get_object_or_404(CustomerProfileConfig, id=profile_id, is_active=True)
		campaign = AudienceService(campaign, serializer.validated_data['default_language'], profile).create_from_manual(
			serializer.validated_data['msisdns'], serializer.validated_data.get('languages')
		)
		return Response({'success': True, 'data': {
			'campaign_id': campaign.id,
			'default_language': campaign.default_language,
			'source_type': campaign.source_type,
			'source_config': campaign.source_config,
			'main_database': campaign.main_database_id,
			'main_table': campaign.main_table,
			'main_msisdn_column': campaign.main_msisdn_column,
			'main_language_column': campaign.main_language_column,
			'file_path': campaign.file_path,
			'file_msisdn_column': campaign.file_msisdn_column,
			'file_language_column': campaign.file_language_column,
			'customer_profile': campaign.customer_profile_id,
			'total_count': campaign.total_count,
			'valid_count': campaign.valid_count,
			'invalid_count': campaign.invalid_count,
			'language_matched': campaign.language_matched,
			'language_defaulted': campaign.language_defaulted,
			'is_processed': campaign.is_processed,
			'processing_started_at': campaign.processing_started_at,
			'processing_completed_at': campaign.processing_completed_at,
		}}, status=status.HTTP_201_CREATED)


class ManualAudienceApiView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Create manual audience configuration', request=ManualAudienceSerializer, responses={201: OpenApiResponse(description='Manual audience configured.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		serializer = ManualAudienceSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			config = AudienceConfig(campaign=campaign)
		config.source_type = 'manual'
		config.manual_msisdns = data['manual_msisdns']
		config.manual_languages = data.get('manual_languages', [])
		config.mapper_enabled = data.get('mapper_enabled', False)
		config.mapper_database_id = data.get('mapper_database_id')
		config.mapper_table = data.get('mapper_table', '')
		config.mapper_msisdn_column = data.get('mapper_msisdn_column', '')
		config.mapper_language_column = data.get('mapper_language_column', '')
		config.mapper_join_type = data.get('mapper_join_type', 'LEFT')
		config.default_language_id = data['default_language_id']
		config.save()
		return Response({'success': True, 'message': 'Manual audience configured.', 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class FileAudienceApiView(APIView):
	parser_classes = [MultiPartParser, FormParser]

	@extend_schema(tags=['Audience Management'], summary='Create file-import audience configuration', request=FileAudienceSerializer, responses={201: OpenApiResponse(description='File audience configured.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		serializer = FileAudienceSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			config = AudienceConfig(campaign=campaign)
		config.source_type = 'file_import'
		config.source_file_path = data.get('file').name
		config.source_file_msisdn_column = data['source_file_msisdn_column']
		config.source_file_language_column = data.get('source_file_language_column', '')
		config.mapper_enabled = data.get('mapper_enabled', False)
		config.mapper_database_id = data.get('mapper_database_id')
		config.mapper_table = data.get('mapper_table', '')
		config.mapper_msisdn_column = data.get('mapper_msisdn_column', '')
		config.mapper_language_column = data.get('mapper_language_column', '')
		config.mapper_join_type = data.get('mapper_join_type', 'LEFT')
		config.default_language_id = data['default_language_id']
		config.save()
		return Response({'success': True, 'message': 'File audience configured.', 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class DatabaseAudienceApiView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Create database audience configuration', request=DatabaseAudienceSerializer, responses={201: OpenApiResponse(description='Database audience configured.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		serializer = DatabaseAudienceSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		config = AudienceConfig.objects.filter(campaign=campaign).first()
		if config is None:
			config = AudienceConfig(campaign=campaign)
		config.source_type = 'database'
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
		config.default_language_id = data['default_language_id']
		config.save()
		return Response({'success': True, 'message': 'Database audience configured.', 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class AudienceBuildView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Build audience members from an audience config id', responses={200: OpenApiResponse(description='Audience build result.')})
	def post(self, request, pk):
		config = get_object_or_404(AudienceConfig, id=pk)
		try:
			result = AudienceBuildService(config).build()
			return Response(result, status=status.HTTP_201_CREATED)
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AudienceConfigCreateView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Get campaign audience config metadata', responses={200: AudienceConfigSerializer})
	def get(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		config, _ = AudienceConfig.objects.get_or_create(campaign=campaign)
		config.default_language_id = config.default_language_id or campaign.default_language_id
		return Response({'success': True, 'data': AudienceConfigSerializer(config).data})

	@extend_schema(tags=['Audience Management'], summary='Create or update campaign audience metadata config', request=AudienceConfigSerializer, responses={201: AudienceConfigSerializer})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		config, _ = AudienceConfig.objects.get_or_create(campaign=campaign)
		serializer = AudienceConfigSerializer(config, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response({'success': True, 'data': AudienceConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class AudienceConfigPreviewView(APIView):
	@extend_schema(tags=['Audience Management'], summary='Preview campaign audience metadata as a JOIN-ready SQL sketch', responses={200: OpenApiResponse(description='Preview result.')})
	def post(self, request, campaign_id):
		campaign = get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
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
		get_object_or_404(Campaign, id=campaign_id, is_deleted=False)
		members = AudienceMember.objects.filter(campaign_id=campaign_id).order_by('sequence_number')
		paginator = StandardPagination()
		page = paginator.paginate_queryset(members, request)
		return paginator.get_paginated_response(AudienceMemberSerializer(page, many=True).data)


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
		build = request.data.get('build_messages', True)
		if isinstance(build, str):
			build = build.lower() not in ('false', '0', 'no')
		result = CampaignActionsService(campaign).activate_campaign(bool(build))
		return Response(result, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)


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

		if settings.KAFKA_ENABLED:
			payload = {key: value[0] if isinstance(value, list) and len(value) == 1 else value
				for key, value in request.data.items()}
			event = enqueue_event('delivery.report.received', payload,
				key=provider_message_id, topic=TOPIC_DLR)
			return Response({'success': True, 'queued': True, 'event_id': event.id},
				status=status.HTTP_202_ACCEPTED)
		if os.getenv('DLR_ASYNC_PROCESSING', '').lower() in ('1', 'true', 'yes'):
			from .models import DeliveryReportInbox
			payload = {
				key: value[0] if isinstance(value, list) and len(value) == 1 else value
				for key, value in request.data.items()
			}
			inbox = DeliveryReportInbox.objects.create(
				provider_message_id=provider_message_id,
				payload=payload,
			)
			return Response({
				'success': True,
				'queued': True,
				'inbox_id': inbox.id,
			}, status=status.HTTP_202_ACCEPTED)

		status_map = {
			'DELIVRD': 'DELIVERED',
			'UNDELIV': 'UNDELIVERABLE',
			'EXPIRED': 'EXPIRED',
			'REJECTD': 'REJECTED',
		}
		mapped_status = status_map.get(provider_status, 'UNKNOWN')
		sent_record = SentRecord.objects.select_related('campaign', 'channel').filter(
			provider_message_id=provider_message_id,
		).first()
		if sent_record is None:
			return Response(
				{'success': False, 'message': 'Unknown provider_message_id.'},
				status=status.HTTP_404_NOT_FOUND,
			)

		delivered_at = request.data.get('delivered_at')
		if delivered_at:
			delivered_at = parse_datetime(str(delivered_at))
			if delivered_at is None:
				return Response(
					{'success': False, 'message': 'Invalid delivered_at timestamp.'},
					status=status.HTTP_400_BAD_REQUEST,
				)

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
	@extend_schema(tags=['Databases'], summary='List database configurations', responses={200: DatabaseConfigSerializer(many=True)})
	def get(self, request):
		queryset = DatabaseConfig.objects.all()
		database_type = request.query_params.get('database_type')
		if database_type:
			queryset = queryset.filter(database_type=database_type)
		return Response({'success': True, 'data': DatabaseConfigSerializer(queryset, many=True).data})

	@extend_schema(tags=['Databases'], summary='Create database configuration', request=DatabaseConfigCreateUpdateSerializer, responses={201: DatabaseConfigSerializer})
	def post(self, request):
		serializer = DatabaseConfigCreateUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		config = serializer.save(created_by=request.user if request.user.is_authenticated else None)
		return Response({'success': True, 'data': DatabaseConfigSerializer(config).data}, status=status.HTTP_201_CREATED)


class DatabaseConfigDetailView(APIView):
	def _config(self, pk):
		return get_object_or_404(DatabaseConfig, pk=pk)

	@extend_schema(tags=['Databases'], summary='Get database configuration', responses={200: DatabaseConfigSerializer})
	def get(self, request, pk):
		return Response({'success': True, 'data': DatabaseConfigSerializer(self._config(pk)).data})

	def _update(self, request, pk, partial):
		config = self._config(pk)
		serializer = DatabaseConfigCreateUpdateSerializer(config, data=request.data, partial=partial)
		serializer.is_valid(raise_exception=True)
		config = serializer.save()
		return Response({'success': True, 'data': DatabaseConfigSerializer(config).data})

	@extend_schema(tags=['Databases'], summary='Replace database configuration', request=DatabaseConfigCreateUpdateSerializer, responses={200: DatabaseConfigSerializer})
	def put(self, request, pk):
		return self._update(request, pk, False)

	@extend_schema(tags=['Databases'], summary='Update database configuration', request=DatabaseConfigCreateUpdateSerializer, responses={200: DatabaseConfigSerializer})
	def patch(self, request, pk):
		return self._update(request, pk, True)

	@extend_schema(tags=['Databases'], summary='Delete database configuration', responses={200: OpenApiResponse(description='Deleted.')})
	def delete(self, request, pk):
		self._config(pk).delete()
		return Response({'success': True, 'message': 'Database configuration deleted successfully.'})


class DatabaseConfigTestView(APIView):
	@extend_schema(tags=['Databases'], summary='Test saved database connection', responses={200: DatabaseConfigTestResponseSerializer})
	def post(self, request, pk):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		result = DatabaseConnector(config).test_connection()
		config.last_tested_at = timezone.now()
		config.last_test_status = 'success' if result['success'] else 'failed'
		config.last_test_message = result['message']
		config.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_message'])
		return Response(result)


class DatabaseConfigTestParamsView(APIView):
	@extend_schema(tags=['Databases'], summary='Test connection without saving', request=DatabaseConfigTestParamsSerializer, responses={200: OpenApiResponse(description='Connection test result.')})
	def post(self, request):
		serializer = DatabaseConfigTestParamsSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		config = DatabaseConfig(**serializer.validated_data, name='temporary-test')
		return Response(DatabaseConnector(config).test_connection())


class DatabaseConfigTablesView(APIView):
	@extend_schema(tags=['Databases'], summary='List external database tables', responses={200: OpenApiResponse(description='Table names.')})
	def get(self, request, pk):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		try:
			tables = DatabaseConnector(config).list_tables()
			return Response({'success': True, 'tables': tables})
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DatabaseConfigColumnsView(APIView):
	@extend_schema(tags=['Databases'], summary='List table columns', responses={200: OpenApiResponse(description='Column metadata.')})
	def get(self, request, pk, table_name):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		try:
			columns = DatabaseConnector(config).list_columns(table_name)
			return Response({'success': True, 'columns': columns})
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DatabaseConfigPreviewView(APIView):
	@extend_schema(tags=['Databases'], summary='Preview table rows', responses={200: OpenApiResponse(description='Sample rows.')})
	def get(self, request, pk, table_name):
		config = get_object_or_404(DatabaseConfig, pk=pk)
		try:
			preview = DatabaseConnector(config).preview_rows(table_name, request.query_params.get('limit', 50))
			return Response({'success': True, **preview})
		except Exception as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CustomerProfilePreviewView(APIView):
	@extend_schema(
		tags=['Databases'],
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
		if Campaign.objects.filter(channels__contains=[channel.code]).exists():
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
class CampaignListCreateView(ListCreateAPIView):
	pagination_class = StandardPagination

	def get_queryset(self):
		queryset = Campaign.objects.filter(is_deleted=False)

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
			from django.db.models import Q
			queryset = queryset.filter(
				Q(name__icontains=search) | Q(sender_id__icontains=search)
			)

		if self.request.query_params.get('mine', '').lower() == 'true':
			queryset = queryset.filter(created_by=self.request.user)

		return annotate_campaign_child_ids(queryset).order_by('-created_at')

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
		if campaign.status not in ('draft', 'invalid_schedule'):
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
		if campaign.status != 'draft':
			return Response(
				{
					'success': False,
					'message': (
						f"Cannot delete campaign in '{campaign.status}' status. "
						'Only draft campaigns can be soft-deleted.'
					),
				},
				status=status.HTTP_400_BAD_REQUEST,
			)
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
		campaign = get_object_or_404(Campaign, id=campaign_id)
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
		if campaign.status not in ('draft', 'invalid_schedule'):
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
		if campaign.status not in ('draft', 'invalid_schedule'):
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


class CampaignBuildMessagesView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='Build MessageObject rows for a campaign', responses={201: OpenApiResponse(description='Build result.')})
	def post(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		round_number = int(request.data.get('round_number', 1))
		batch_id = request.data.get('batch_id')
		try:
			result = MessageBuilder(campaign=campaign, round_number=round_number, batch_id=batch_id).build()
		except ValueError as exc:
			return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
		except Exception as exc:
			return Response({'success': False, 'message': f'Build failed: {exc}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
		return Response({'success': True, 'message': 'Messages built successfully.', 'data': result}, status=status.HTTP_201_CREATED)


class CampaignMessagesListView(APIView):
	@extend_schema(tags=['Campaign Messages'], summary='List MessageObject rows for a campaign', responses={200: OpenApiResponse(description='Message list.')})
	def get(self, request, pk):
		campaign = get_object_or_404(Campaign, pk=pk, is_deleted=False)
		qs = MessageObject.objects.filter(campaign=campaign).order_by('id').select_related('language', 'channel')
		status_filter = request.query_params.get('status')
		if status_filter:
			qs = qs.filter(sent_status=status_filter)
		# The project model stores the queue lifecycle on `sent_status` and
		# `delivery_status`, not on a separate `status` attribute. Keep list
		# serialization against the live field names.
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
				'message_parts': m.message_parts,
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
