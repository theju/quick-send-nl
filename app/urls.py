from django.urls import path
from .views import index, upload_csv, compose_message, pick_send_mode, confirm_send, \
    send_mails, send_status, google_oauth_access_token

urlpatterns = [
    path('', index, name='index'),
    path('upload-csv/', upload_csv, name='upload_csv'),
    path('compose-message/', compose_message, name='compose_message'),
    path('send-mode/', pick_send_mode, name='pick_send_mode'),
    path('confirm-send/', confirm_send, name='confirm_send'),
    path('send/', send_mails, name='send_mails'),
    path('status/', send_status, name='send_status'),

    path('google-oauth-access-token/', google_oauth_access_token, name='google_oauth_access_token'),
]
