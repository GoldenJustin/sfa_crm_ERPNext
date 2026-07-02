import frappe
import json
import traceback
import time

def get_single_val(doctype, fieldname):
    res = frappe.db.sql("SELECT value FROM tabSingles WHERE doctype=%s AND field=%s", (doctype, fieldname))
    return res[0][0] if res else None

def resolve_customer_or_lead(input_name):
    if frappe.db.exists("Customer", input_name): return "Customer", input_name
    cust = frappe.db.get_value("Customer", {"customer_name": input_name}, "name")
    if cust: return "Customer", cust
    if frappe.db.exists("Lead", input_name): return "Lead", input_name
    lead = frappe.db.get_value("Lead", {"lead_name": input_name}, "name")
    if lead: return "Lead", lead
    return None, None

def process_base64_image(base64_data, doctype, docname, fieldname=None):
    if "," in base64_data: base64_data = base64_data.split(",")[1]
    file_doc = frappe.get_doc({
        "doctype": "File", "file_name": f"img_{int(time.time())}_{frappe.generate_hash(length=4)}.jpg",
        "attached_to_doctype": doctype, "attached_to_name": docname,
        "content": base64_data, "decode": True, "is_private": 0
    })
    file_doc.insert(ignore_permissions=True)
    if fieldname:
        frappe.db.sql(f"UPDATE `tab{doctype}` SET `{fieldname}`=%s WHERE name=%s", (file_doc.file_url, docname))

def convert_lead_to_customer(lead_id, company):
    lead = frappe.get_doc("Lead", lead_id)
    cust = frappe.new_doc("Customer")
    cust.customer_name = lead.lead_name or lead.company_name or lead.first_name
    cust.lead_name = lead.name
    cust.company = company
    
    cg = get_single_val("Selling Settings", "customer_group")
    if not cg:
        cg_list = frappe.db.get_all("Customer Group", limit=1)
        cg = cg_list[0].name if cg_list else "Commercial"
    cust.customer_group = cg
    
    cust.territory = lead.territory
    cust.custom_latitude = lead.custom_latitude
    cust.custom_longitude = lead.custom_longitude
    cust.mobile_no = lead.mobile_no
    
    cust.image = lead.image
    cust.custom_storefront = lead.image 
    cust.custom_business_type = getattr(lead, 'custom_business_type', None)
    
    cust.flags.ignore_mandatory = True
    cust.insert(ignore_permissions=True)
    frappe.db.sql("UPDATE `tabLead` SET status='Converted' WHERE name=%s", (lead.name,))
    return cust.name

@frappe.whitelist(allow_guest=True)
def get_site_logo():
    logo = get_single_val("Website Settings", "app_logo") or get_single_val("Website Settings", "banner_image")
    if logo: return {"logo_url": frappe.utils.get_url(logo)}
    return {"logo_url": None}

@frappe.whitelist(allow_guest=True)
def sfa_login(usr, pwd):
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
        frappe.local.response.message = {"message": "Logged In", "home_page": "/app", "full_name": frappe.session.user_full_name}
    except Exception:
        frappe.local.response['http_status_code'] = 401
        frappe.local.response['message'] = "Invalid Credentials"

@frappe.whitelist()
def get_sfa_settings():
    try:
        logo = get_single_val("Website Settings", "app_logo") or get_single_val("Website Settings", "banner_image")
        company_name = get_single_val("SFA Settings", "company_name_override")
        if not company_name: company_name = frappe.defaults.get_user_default("Company")
        if not company_name:
            c_list = frappe.db.get_all("Company", limit=1)
            company_name = c_list[0].name if c_list else "Koda Technologies"
            
        # Hard override if the DB defaults to AKO GROUP
        if company_name == "AKO GROUP": company_name = "Koda Technologies"

        enable_del = get_single_val("SFA Settings", "enable_delivery_module") or 0
        enable_exp = get_single_val("SFA Settings", "enable_expense_module") or 0

        return {
            "logo_url": frappe.utils.get_url(logo) if logo else None,
            "company_name": company_name,
            "enable_delivery_module": int(enable_del),
            "enable_expense_module": int(enable_exp)
        }
    except Exception:
        return {"logo_url": None, "company_name": "Koda Technologies", "enable_delivery_module": 0, "enable_expense_module": 0}

@frappe.whitelist()
def sync_client(payload):
    data = json.loads(payload)
    try:
        doc = frappe.new_doc("Lead")
        doc.first_name = data.get("name", "Unknown")
        doc.lead_name = data.get("name", "Unknown")
        
        comp_list = frappe.db.get_all("Company", limit=1)
        doc.company = frappe.defaults.get_user_default("Company") or (comp_list[0].name if comp_list else None)
        
        t_list = frappe.db.get_all("Territory", limit=1)
        doc.territory = t_list[0].name if t_list else "All Territories"
        
        doc.mobile_no = data.get("phone")
        doc.phone = data.get("phone")
        doc.custom_business_type = data.get("businessType")
        doc.custom_latitude = data.get("lat")
        doc.custom_longitude = data.get("lng")
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)

        notes = data.get("notes", "")
        role = data.get("contactRole", "")
        owner_phone = data.get("ownerPhone", "")
        comment_text = f"**KYC Details**\nRole: {role}\nOwner Phone: {owner_phone}\n\n**Observations:**\n{notes}"
        doc.add_comment("Comment", text=comment_text)

        photos = data.get("photosBase64", [])
        for i, photo_b64 in enumerate(photos):
            fname = "image" if i == 0 else None
            process_base64_image(photo_b64, "Lead", doc.name, fname)

        frappe.db.commit()
        return {"success": True, "name": doc.name}
    except Exception as e: return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def sync_visit(payload):
    data = json.loads(payload)
    try:
        doctype_found, docname_found = resolve_customer_or_lead(data.get("customer"))
        if not doctype_found: return {"success": False, "error": f"Client '{data.get('customer')}' not found."}
        
        comp_list = frappe.db.get_all("Company", limit=1)
        company = frappe.defaults.get_user_default("Company") or (comp_list[0].name if comp_list else None)

        if doctype_found == "Lead": docname_found = convert_lead_to_customer(docname_found, company)

        doc = frappe.get_doc({
            "doctype": "Visit Log", "sales_person": frappe.session.user, "customer": docname_found,
            "start_time": data.get("start_time", "").replace("T", " ")[:19], "end_time": data.get("end_time", "").replace("T", " ")[:19],
            "outcome": data.get("outcome"), "no_order_reason": data.get("no_order_reason"),
            "custom_latitude": data.get("lat"), "custom_longitude": data.get("lng")
        })
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)

        if data.get("photoBase64"):
            process_base64_image(data.get("photoBase64"), "Visit Log", doc.name, "evidence_photo")

        frappe.db.commit()
        return {"success": True, "name": doc.name}
    except Exception as e: return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def sync_order(doc_type, payload):
    data = json.loads(payload)
    try:
        doctype_found, docname_found = resolve_customer_or_lead(data.get("customer"))
        if not doctype_found: return {"success": False, "error": f"Customer/Lead '{data.get('customer')}' not found."}
        
        comp_list = frappe.db.get_all("Company", limit=1)
        company = frappe.defaults.get_user_default("Company") or (comp_list[0].name if comp_list else None)
        
        if doctype_found == "Lead": docname_found = convert_lead_to_customer(docname_found, company)
            
        data["customer"] = docname_found
        data["company"] = company
        data["doctype"] = doc_type
        data["docstatus"] = 1
        
        doc = frappe.get_doc(data)
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        return {"success": True, "name": doc.name}
    except Exception as e: return {"success": False, "error": str(e), "trace": traceback.format_exc()}

@frappe.whitelist()
def force_log_location(latitude, longitude, timestamp, activity):
    try:
        frappe.get_doc({"doctype": "Salesperson Location Log", "sales_person": frappe.session.user, "latitude": latitude, "longitude": longitude, "timestamp": timestamp, "activity": activity}).insert(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success"}
    except Exception: return {"status": "error"}

def set_default_company(doc, method):
    if not doc.company:
        comp_list = frappe.db.get_all('Company', limit=1)
        doc.company = frappe.defaults.get_user_default('Company') or (comp_list[0].name if comp_list else None)

