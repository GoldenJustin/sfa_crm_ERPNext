app_name = "sfa_crm"
app_title = "Sfa Crm"
app_publisher = "Koda Technologies"
app_description = "ERPNext App that help to manage Fieldforce SFA"
app_email = "justinemsengi@gmail.com"
app_license = "mit"

# Allow the mobile app to hit login endpoint without being logged in
allow_guest_to_call = [
    "sfa_crm.api.sfa_login",
    "sfa_crm.api.get_site_logo"
]

# Include CSS
app_include_css = "/assets/sfa_crm/css/sfa_crm.css"

# Document Events
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

# Fixtures
fixtures = [
    {"dt": "Client Script", "filters": [["dt", "in", [
        "Customer Territory Map",
        "Sales Team Tracker",
        "Salesperson Location Log"
    ]]]},
    {"dt": "Report", "filters": [["module", "=", "Sfa Crm"]]},
    {"dt": "DocType", "filters": [["module", "=", "Sfa Crm"], ["custom", "=", 1]]},
]
