app_name = "sfa_crm"
app_title = "Sfa Crm"
app_publisher = "Koda Technologies"
app_description = "ERPNext App that help to manage Fieldforce SFA"
app_email = "justinemsengi@gmail.com"
app_license = "mit"

# required_apps = []

# Allow the mobile app to hit our custom login endpoint without being logged in
allow_guest_to_call = [
    "sfa_crm.api.sfa_login"
]

# Include JS/CSS
app_include_css = "/assets/sfa_crm/css/sfa_crm.css"

doc_events = {
    "Sales Order": {
        "before_validate": "sfa_crm.api.set_default_company"
    },
    "Quotation": {
        "before_validate": "sfa_crm.api.set_default_company"
    },
    "Payment Entry": {
        "before_validate": "sfa_crm.api.set_default_company"
    }
}
fixtures = ["Report", "Custom Field", "Property Setter"]
