import os
import time
import base64
import random

import rq
import redis
import django_rq
import requests

from urllib.parse import urlencode

from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

from django.urls import reverse
from django.conf import settings
from django.shortcuts import render
from django.template import Template, Context
from django.utils.translation import gettext as _
from django.contrib.sessions.models import Session
from django.core.mail import EmailMultiAlternatives, get_connection
from django.http import HttpResponseRedirect, HttpResponseBadRequest

from .forms import UploadCSVForm, ComposeMessageForm, ModeForm, \
    GoogleOAuthForm, SMTPForm


def index(request):
    return HttpResponseRedirect(reverse('upload_csv'))


def upload_csv(request):
    form = UploadCSVForm()
    if request.method == 'POST':
        form = UploadCSVForm(request.POST, request.FILES)
        if form.is_valid():
            # Save form's data in the session
            request.session.pop('compose', None)
            request.session.pop('smtp', None)
            request.session.pop('confirm_viewed', None)
            csv_file = form.cleaned_data['csv_file']
            request.session['csv'] = [ii for ii in csv_file]
            request.session['email_field'] = form.cleaned_data['email_field']
            # Keep at max for 3600 seconds in the session
            request.session.set_expiry(3600)
            return HttpResponseRedirect(reverse('compose_message'))
    return render(request, 'upload_csv.html', {
        'form': form
    })


def compose_message(request):
    if not request.session.get('csv'):
        return HttpResponseRedirect(reverse('upload_csv'))

    form = ComposeMessageForm(request.session.get('compose'))
    if request.method == 'POST':
        form = ComposeMessageForm(request.POST)
        if form.is_valid():
            request.session['compose'] = form.cleaned_data
            return HttpResponseRedirect(reverse('pick_send_mode'))
    return render(request, 'compose_message.html', {
        'form': form
    })


def pick_send_mode(request):
    if not request.session.get('csv'):
        return HttpResponseRedirect(reverse('upload_csv'))

    if not request.session.get('compose'):
        return HttpResponseRedirect(reverse('compose_message'))

    form = ModeForm()
    if request.method == 'POST':
        data = {'mode': request.POST.get('mode')}
        form = ModeForm(data)
        if not form.is_valid():
            return render(request, 'pick_send_mode.html', {'form': form})

        if form.cleaned_data['mode'] == 'google':
            form = GoogleOAuthForm(request.POST)
        else:
            form = SMTPForm(request.POST)
        if form.is_valid():
            request.session['mode'] = request.POST['mode']
            request.session['smtp'] = form.cleaned_data
            return HttpResponseRedirect(reverse('confirm_send'))
    else:
        if request.session.get('mode') == 'google':
            form = GoogleOAuthForm(request.session.get('smtp'))
        else:
            form = SMTPForm(request.session.get('smtp'))

    google_oauth_link = None
    if getattr(settings, 'GOOGLE_OAUTH'):
        state = str(int(random.random() * 1000))
        request.session['state'] = state
        client_id = settings.GOOGLE_OAUTH['CLIENT_ID']
        redirect_uri = request.build_absolute_uri(reverse('google_oauth_access_token'))
        client_secret = settings.GOOGLE_OAUTH['CLIENT_SECRET']
        params = urlencode({
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'https://www.googleapis.com/auth/gmail.send',
            'state': state
        })
        google_oauth_link = 'https://accounts.google.com/o/oauth2/v2/auth?{0}'.format(params)

    return render(request, 'pick_send_mode.html', {
        'form': form,
        'google_oauth_link': google_oauth_link
    })


def confirm_send(request):
    if not request.session.get('csv'):
        return HttpResponseRedirect(reverse('upload_csv'))

    if not request.session.get('compose'):
        return HttpResponseRedirect(reverse('compose_message'))

    if not request.session.get('smtp'):
        return HttpResponseRedirect(reverse('pick_send_mode'))

    random_row = random.choice(request.session['csv'])
    email_field = request.session['email_field']
    random_recipient = random_row[email_field]

    compose = request.session['compose']
    ctx = Context(random_row)
    preview_subject = Template(compose['subject']).render(ctx)
    preview_txt_msg = Template(compose['txt_msg']).render(ctx)
    preview_html_msg = Template(compose['html_msg']).render(ctx)

    request.session['confirm_viewed'] = True

    return render(request, 'confirm_send.html', {
        'total_rows': len(request.session['csv']),
        'random_recipient': random_recipient,
        'preview_subject': preview_subject,
        'preview_txt_msg': preview_txt_msg,
        'preview_html_msg': preview_html_msg,
    })


def send_mails(request):
    if not request.session.get('csv'):
        return HttpResponseRedirect(reverse('upload_csv'))

    if not request.session.get('compose'):
        return HttpResponseRedirect(reverse('compose_message'))

    if not request.session.get('smtp'):
        return HttpResponseRedirect(reverse('pick_send_mode'))

    if not request.session.get('confirm_viewed'):
        return HttpResponseRedirect(reverse('confirm_send'))

    if request.session['mode'] == 'google':
        send_mails_google(request)
    else:
        send_mails_smtp(request)

    return HttpResponseRedirect(reverse('send_status'))


def send_status(request):
    rconn = redis.Redis(
        settings.REDIS['host'],
        settings.REDIS['port'],
        settings.REDIS['password']
    )
    status = ''
    job_ids = rconn.keys('rq:job:*')
    session_id = request.session.session_key
    done = False
    for jid in job_ids:
        job = rq.job.Job.fetch(
            jid.decode().replace('rq:job:', ''),
            connection=rconn
        )
        if job.meta.get('session_id') == session_id and job.result:
            if job.result == True:
                status = _('Queued all emails') + '\r\n' + status
                done = True
                break
            status = str(job.result) + '\r\n' + status
    status = status.strip()
    return render(request, 'status.html', {
        'status': status,
        'done': done
    })


def google_oauth_access_token(request):
    if request.session.get('state') != request.GET.get('state'):
        return HttpResponseBadRequest('Invalid state')

    request.session.pop('state', None)

    client_id = settings.GOOGLE_OAUTH['CLIENT_ID']
    redirect_uri = request.build_absolute_uri(reverse('google_oauth_access_token'))
    client_secret = settings.GOOGLE_OAUTH['CLIENT_SECRET']
    auth_code = request.GET.get('code')
    auth_params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
        'access_type': 'offline',
        'code': auth_code
    }
    response = requests.post(
        'https://www.googleapis.com/oauth2/v4/token', data=auth_params
    )
    json_resp = response.json()
    if not response.ok:
        return HttpResponseBadRequest('Failed to get access token')
    request.session['mode'] = 'google'
    request.session['smtp'] = {'access_token': json_resp['access_token']}
    return HttpResponseRedirect(reverse('confirm_send'))


def send_mails_google(request):
    queue_name = os.path.basename(settings.BASE_DIR)
    queue = django_rq.get_queue(queue_name)
    for (idx, row) in enumerate(request.session['csv']):
        kwargs = {
            'idx': idx,
            'row': row,
            'session': request.session,
            'mode': 'google',
        }
        queue.enqueue(send_msg, **kwargs)


def send_mails_smtp(request):
    queue_name = os.path.basename(settings.BASE_DIR)
    queue = django_rq.get_queue(queue_name)

    for (idx, row) in enumerate(request.session['csv']):
        kwargs = {
            'idx': idx,
            'row': row,
            'session': request.session,
            'mode': 'smtp',
        }
        queue.enqueue(send_msg, ttl=100, **kwargs)


def send_msg(**kwargs):
    session = kwargs['session']
    session_id = session.session_key
    compose = session['compose']
    email_field = session['email_field']
    total_emails = len(session['csv'])
    recipient = kwargs['row'][session['email_field']]

    ctx = Context(kwargs['row'])
    subject = Template(compose['subject']).render(ctx)
    txt_msg = Template(compose['txt_msg']).render(ctx)
    html_msg = Template(compose['html_msg']).render(ctx)
    msg = EmailMultiAlternatives(subject, txt_msg, compose['sender'], [recipient])
    msg.attach_alternative(html_msg, 'text/html')

    job = rq.get_current_job()
    job.meta['session_id'] = session_id
    job.save_meta()

    if kwargs['mode'] == 'google':
        msg_str = msg.message().as_string()
        raw_msg = base64.urlsafe_b64encode(msg_str.encode()).decode()

        response = requests.post(
            'https://www.googleapis.com/gmail/v1/users/me/messages/send',
            json={'raw': raw_msg},
            headers={
                'Authorization': 'Bearer {0}'.format(session['smtp']['access_token']),
                'Content-Type': 'application/json'
            }
        )
        if not response.ok:
            status = response.content.decode()
            return status
    else:
        smtp = session['smtp']
        connection = {
            'host': smtp['host'],
            'port': smtp['port'],
            'username': smtp['username'],
            'password': smtp['password'],
            'use_tls': smtp['use_tls'],
        }

        msg.connection = get_connection(**connection)
        try:
            msg.send()
        except Exception as ex:
            status = ex.strerror
            return status

    idx = kwargs['idx']
    total_emails = len(session['csv'])

    status = _('{0}% sent.'.format((idx + 1) / total_emails * 100)) + '\r\n'
    status += _('Sent mail to {0}'.format(recipient)) + '\r\n'

    if idx + 1 == total_emails:
        queue_name = os.path.basename(settings.BASE_DIR)
        queue = django_rq.get(queue_name)
        queue.enqueue(delete_session, session_id)
        status = True
    return status


def delete_session(session_id):
    time.sleep(30)
    Session.objects.get(session_key=session_id).delete()
