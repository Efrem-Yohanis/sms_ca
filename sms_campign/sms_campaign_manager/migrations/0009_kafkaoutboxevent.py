from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies = [('sms_campaign_manager', '0008_deliveryreportinbox')]
    operations = [migrations.CreateModel(
        name='KafkaOutboxEvent',
        fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('event_type', models.CharField(db_index=True, max_length=150)),
            ('topic', models.CharField(max_length=250)),
            ('key', models.CharField(blank=True, default='', max_length=250)),
            ('payload', models.JSONField(default=dict)),
            ('status', models.CharField(choices=[('pending','Pending'),('published','Published'),('failed','Failed')], db_index=True, default='pending', max_length=20)),
            ('attempts', models.PositiveIntegerField(default=0)),
            ('last_error', models.TextField(blank=True, default='')),
            ('available_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
            ('published_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
        ],
        options={'ordering':['id'], 'indexes': [
            models.Index(fields=['status','available_at'], name='sms_kafka_status_avail_idx'),
            models.Index(fields=['event_type','status'], name='sms_kafka_event_status_idx'),
        ]},
    )]
