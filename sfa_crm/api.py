import frappe
import json

def set_default_company(doc, method=None):
    if hasattr(doc, "company") and not doc.get("company"):
        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
            or frappe.db.get_value("Company", {}, "name")
        )
        if company:
            doc.company = company

@frappe.whitelist(allow_guest=True)
def sfa_login(usr, pwd):
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.exceptions.AuthenticationError:
        frappe.db.set_value("User", usr, "last_login", None, update_modified=False)
        frappe.local.response['http_status_code'] = 401
        frappe.local.response['message'] = "Invalid Login Credentials"
        return
    except Exception as e:
        frappe.log_error(title="SFA Login Exception", message=frappe.get_traceback())
        frappe.local.response['http_status_code'] = 500
        frappe.local.response['message'] = "Server error during login."
        return

    # === TEMPORARILY DISABLED ROLE CHECK FOR PRESENTATION ===
    # user_roles = frappe.get_roles(frappe.session.user)
    # if "SFA Mobile User" not in user_roles:
    #     login_manager.logout()
    #     frappe.local.response['http_status_code'] = 403
    #     frappe.local.response['message'] = "User missing 'SFA Mobile User' role."
    #     return
    # ========================================================

    frappe.local.response.message = {
        "message": "Logged In",
        "home_page": "/app",
        "full_name": frappe.session.user_full_name
    }

@frappe.whitelist(allow_guest=False)
def create_erp_document(payload):
    try:
        data = json.loads(payload)
        if not data.get("company"):
            company = frappe.db.get_value("Company", {}, "name")
            if not company:
                frappe.throw("No Company found in ERPNext database!")
            data["company"] = company
        
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        if data.get("docstatus") == 1:
            doc.submit()
        return doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SFA CRM Sync Error")
        raise

@frappe.whitelist()
def get_sfa_settings():
    try:
        settings = frappe.get_doc("SFA Settings")
        user = frappe.session.user
        user_roles = frappe.get_roles(user)
        
        disabled_features = set()

        for p in settings.permissions:
            if p.disabled:
                is_match = (p.apply_to == 'User' and p.user_or_role == user) or \
                           (p.apply_to == 'Role' and p.user_or_role in user_roles)
                if is_match:
                    disabled_features.add(p.feature.lower().replace(" ", "_"))
        
        return {
            "logo_url": settings.app_logo,
            "company_name": settings.company_name_override,
            "disabled_features": list(disabled_features)
        }
    except frappe.DoesNotExistError:
        return {
            "logo_url": None,
            "company_name": None,
            "disabled_features": []
        }
