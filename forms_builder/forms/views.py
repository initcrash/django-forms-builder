
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.sites.models import Site
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.http import urlquote
from email_extras.utils import send_mail_template

from forms_builder.forms.forms import FormForForm
from forms_builder.forms.models import Form
from forms_builder.forms.settings import SEND_FROM_SUBMITTER
from forms_builder.forms.signals import form_invalid, form_valid


class FormDetailView(object):
    def __call__(self, request, slug, template="forms/form_detail.html"):
        """
        Display a built form and handle submission.
        """
        published = Form.objects.published(for_user=request.user)
        form = get_object_or_404(published, slug=slug)
        if form.login_required and not request.user.is_authenticated():
            return redirect("%s?%s=%s" % (
                settings.LOGIN_URL,
                REDIRECT_FIELD_NAME,
                urlquote(request.get_full_path())
            ))
        request_context = RequestContext(request)
        args = (
            form, request_context,
            request.POST or None,
            request.FILES or None
        )
        form_for_form = FormForForm(*args)
        if request.method == "POST":
            if not form_for_form.is_valid():
                form_invalid.send(sender=request, form=form_for_form)
            else:
                entry = form_for_form.save()
                self.email(request, form, form_for_form, entry)
                form_valid.send(
                    sender=request,
                    form=form_for_form,
                    entry=entry
                )
                return redirect(reverse("form_sent", kwargs={
                    "slug": form.slug
                }))
        context = {"form": form}
        return render_to_response(template, context, request_context)

    def email_subject(self, request, form, entry):
        subject = form.email_subject
        if not subject:
            subject = "%s - %s" % (form.title, entry.entry_time)
        return subject

    def email_context(self, request, form, form_for_form):
        fields = [(v.label, form_for_form.cleaned_data[k])
                  for (k, v) in form_for_form.fields.items()]
        context = {
            "fields": fields,
            "message": form.email_message,
            "request": request,
        }
        return context

    def email_template(self):
        return 'form_response'

    def send_email(self,
        subject, email_to, email_from,
        context, form_for_form):

        attachments = []
        for f in form_for_form.files.values():
            f.seek(0)
            attachments.append((f.name, f.read()))

        send_mail_template(subject, self.email_template(), email_from,
                           email_to, context=context,
                           attachments=attachments,
                           fail_silently=settings.DEBUG)

    def email(self, request, form, form_for_form, entry):
        subject = self.email_subject(request, form, entry)
        email_from = form.email_from or settings.DEFAULT_FROM_EMAIL
        email_to = form_for_form.email_to()
        context = self.email_context(request, form, form_for_form)

        if SEND_FROM_SUBMITTER:
            # Send from the email entered.
            email_from = email_to

        if email_to and form.send_email:
            self.send_email(
                subject,
                email_to,
                email_from,
                context,
                form_for_form
            )

        email_copies = [e.strip() for e in form.email_copies.split(",")
                        if e.strip()]

        for email_to in email_copies:

            self.send_email(
                subject,
                email_to,
                email_from,
                context,
                form_for_form
            )

form_detail = FormDetailView()


def form_sent(request, slug, template="forms/form_sent.html"):
    """
    Show the response message.
    """
    published = Form.objects.published(for_user=request.user)
    form = get_object_or_404(published, slug=slug)
    context = {"form": form}
    return render_to_response(template, context, RequestContext(request))
