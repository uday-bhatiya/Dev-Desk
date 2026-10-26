from django import forms

from .models import Category, Ticket


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "category", "description"]
        labels = {"title": "Summary"}
        help_texts = {"title": "A short description of the problem."}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Select a category"

    def clean_title(self):
        title = self.cleaned_data["title"]  
        if len(title) < 5:
            raise forms.ValidationError("Please enter at least 5 characters.")
        return title

    def clean_description(self):
        description = self.cleaned_data["description"]
        if len(description) < 10:
            raise forms.ValidationError(
                "Please describe the problem in at least 10 characters."
            )
        return description