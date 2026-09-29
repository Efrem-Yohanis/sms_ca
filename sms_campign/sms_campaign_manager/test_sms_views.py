"""Standalone Test SMS API; this flow never enters campaign delivery tables."""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiResponse, extend_schema

from .models import Channel, SenderID, TestMessage
from .serializers import (
    CreateTestMessageSerializer,
    TestMessageListSerializer,
    TestMessageSerializer,
)
from .services.test_sms import send_test_to_smsc


def _store_test_message(request, values):
    result = send_test_to_smsc(
        values['sender_id'],
        values['recipient'],
        values['channel_code'],
        values['message_content'],
        values['test_campaign_id'],
    )
    if result.get('config_missing'):
        return None

    created_by = getattr(request, 'user', None)
    if not getattr(created_by, 'is_authenticated', False):
        created_by = None
    return TestMessage.objects.create(
        **values,
        provider_message_id=result['provider_message_id'],
        provider_status=result['provider_status'],
        http_status=result['http_status'],
        accepted=result['accepted'],
        duration_ms=result['duration_ms'],
        request_url=result['request_url'],
        request_method=result['request_method'],
        request_payload=result['request_payload'],
        response_payload=result['response_payload'],
        error_message=result['error_message'],
        created_by=created_by,
    )


def _config_missing_response():
    return Response({
        'success': False,
        'errors': {'smsc_config': ['No active SMSC configuration. Configure one first.']},
    }, status=status.HTTP_502_BAD_GATEWAY)


def _validate_submission(data):
    serializer = CreateTestMessageSerializer(data=data)
    if not serializer.is_valid():
        return None, Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    values = serializer.validated_data
    if not SenderID.objects.filter(sender_id=values['sender_id'], is_active=True).exists():
        error = f"'{values['sender_id']}' is not a registered, active Sender ID."
        return None, Response({'success': False, 'errors': {'sender_id': [error]}}, status=status.HTTP_400_BAD_REQUEST)
    if not Channel.objects.filter(code=values['channel_code'], is_active=True).exists():
        error = f"'{values['channel_code']}' is not a valid active channel."
        return None, Response({'success': False, 'errors': {'channel_code': [error]}}, status=status.HTTP_400_BAD_REQUEST)
    return values, None


class TestMessageListCreateView(APIView):
    @extend_schema(tags=['Test SMS'], summary='List recent standalone SMS tests')
    def get(self, request):
        queryset = TestMessage.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(recipient__icontains=search) | Q(message_content__icontains=search))

        accepted_filter = request.query_params.get('accepted')
        if accepted_filter is not None:
            normalized = accepted_filter.strip().lower()
            if normalized not in {'true', 'false'}:
                return Response({
                    'success': False,
                    'errors': {'accepted': ['Use true or false.']},
                }, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(accepted=(normalized == 'true'))

        try:
            limit = min(max(int(request.query_params.get('limit', 10)), 1), 100)
            offset = max(int(request.query_params.get('offset', 0)), 0)
        except (TypeError, ValueError):
            return Response({
                'success': False,
                'errors': {'pagination': ['limit and offset must be integers.']},
            }, status=status.HTTP_400_BAD_REQUEST)

        count = queryset.count()
        rows = queryset.order_by('-created_at', '-id')[offset:offset + limit]
        return Response({
            'success': True,
            'count': count,
            'results': TestMessageListSerializer(rows, many=True).data,
        })

    @extend_schema(tags=['Test SMS'], summary='Send and record a test SMS', request=CreateTestMessageSerializer, responses={201: TestMessageSerializer, 400: OpenApiResponse(description='Validation error.'), 502: OpenApiResponse(description='No active SMSC configuration.')})
    def post(self, request):
        values, error_response = _validate_submission(request.data)
        if error_response:
            return error_response
        row = _store_test_message(request, values)
        if row is None:
            return _config_missing_response()
        return Response({'success': True, 'data': TestMessageSerializer(row).data}, status=status.HTTP_201_CREATED)


class TestMessageDetailView(APIView):
    @extend_schema(tags=['Test SMS'], summary='Read a test SMS and its SMSC exchange', responses={200: TestMessageSerializer})
    def get(self, request, pk):
        row = get_object_or_404(TestMessage, pk=pk)
        return Response({'success': True, 'data': TestMessageSerializer(row).data})

    @extend_schema(tags=['Test SMS'], summary='Delete a test SMS', responses={204: OpenApiResponse(description='Test SMS deleted.')})
    def delete(self, request, pk):
        row = get_object_or_404(TestMessage, pk=pk)
        row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TestMessageResendView(APIView):
    @extend_schema(tags=['Test SMS'], summary='Resend a test SMS as a new record', responses={201: TestMessageSerializer, 502: OpenApiResponse(description='No active SMSC configuration.')})
    def post(self, request, pk):
        original = get_object_or_404(TestMessage, pk=pk)
        values = {
            'sender_id': original.sender_id,
            'recipient': original.recipient,
            'channel_code': original.channel_code,
            'message_content': original.message_content,
            'test_campaign_id': original.test_campaign_id,
        }
        row = _store_test_message(request, values)
        if row is None:
            return _config_missing_response()
        return Response({'success': True, 'data': TestMessageSerializer(row).data}, status=status.HTTP_201_CREATED)