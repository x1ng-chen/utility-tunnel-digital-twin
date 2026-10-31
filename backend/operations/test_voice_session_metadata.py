from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase,override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from .models import Profile


@override_settings(API_TOKEN_TTL_SECONDS=900,API_TOKEN_RENEWAL_WINDOW_SECONDS=60)
class VoiceSessionMetadataTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='voice-metadata-test',email='metadata@test.invalid',password='Metadata-tests-only-987654321')
        Profile.objects.create(user=self.user,role=Profile.Role.VIEWER)
        self.client=APIClient()

    def login(self):
        return self.client.post('/api/auth/login/',{'email':'metadata@test.invalid','password':'Metadata-tests-only-987654321'},format='json')

    def test_new_login_reports_actual_server_token_expiry(self):
        response=self.login()
        self.assertEqual(response.status_code,200)
        token=Token.objects.get(user=self.user)
        data=response.json()
        self.assertEqual(parse_datetime(data['tokenExpiresAt']),token.created+timedelta(seconds=900))
        self.assertTrue(895<=data['tokenExpiresIn']<=900)
        self.assertEqual(data['user']['role'],'viewer')

    def test_reused_token_reports_original_expiry_instead_of_fresh_ttl(self):
        token=Token.objects.create(user=self.user)
        token.created=timezone.now()-timedelta(seconds=300)
        token.save(update_fields=['created'])
        response=self.login()
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['accessToken'],token.key)
        self.assertEqual(parse_datetime(data['tokenExpiresAt']),token.created+timedelta(seconds=900))
        self.assertTrue(595<=data['tokenExpiresIn']<=600)
