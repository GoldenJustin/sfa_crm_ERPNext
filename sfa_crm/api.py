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
