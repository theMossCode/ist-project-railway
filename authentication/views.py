import logging

from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib.auth import get_user_model, get_user
from django.urls import reverse
from django.forms import ValidationError

from .forms import SignUpForm


def signup_view(request):
    if request.method == "POST":
        err = ""
        form = SignUpForm(request.POST)
        logging.debug(form)
        try:
            if form.is_valid():
                if get_user_model().objects.filter(username=form.cleaned_data["username"]).exists():
                    err = "Username already exists!"
                    raise ValidationError("User Exists")
                elif get_user_model().objects.filter(email=form.cleaned_data["email"]).exists():
                    err = "Email already exists!"
                    raise ValidationError("email Exists")

                new_user = get_user_model().objects.create_user(form.cleaned_data["username"],
                                                                form.cleaned_data["email"],
                                                                form.cleaned_data["password"])
                if new_user is not None:
                    logging.debug("User created {}".format(new_user.username))
                    return HttpResponseRedirect(reverse("authentication:login"))

        except Exception as e:
            if len(err) == 0:
                err = "Unknown error!"
            print(e)
            return render(request, "authentication/signup.html", {"form": form, "err": err})

    else:
        form = SignUpForm()

    return render(request, "authentication/signup.html", {"form": form})
