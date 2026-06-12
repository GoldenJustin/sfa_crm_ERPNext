import frappe
import json

@frappe.whitelist(allow_guest=False)
def create_erp_document(payload):
    """
    Takes a raw JSON payload from the mobile app, forcefully injects the company,
    and creates the document while bypassing strict REST API permission blocks.
    """
    try:
        data = json.loads(payload)
        
        # 1. Forcefully inject the Company before Frappe validates anything!
        if not data.get("company"):
            company = frappe.db.get_value("Company", {}, "name")
            if not company:
                frappe.throw("No Company found in ERPNext database!")
            data["company"] = company
            
        # 2. Instantiate the document
        doc = frappe.get_doc(data)
        
        # 3. Save it to the database (ignoring role permission blocks)
        doc.insert(ignore_permissions=True)
        
        # 4. If the app requested it to be Submitted (docstatus 1), submit it!
        if data.get("docstatus") == 1:
            doc.submit()
            
        return doc.name

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "SFA CRM Sync Error")
        frappe.throw(str(e))
