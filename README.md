### Sfa Crm

ERPNext App that help to manage Fieldforce SFA

**Compatible with ERPNext v15 and v16**

### Requirements

- Frappe **v15 or v16** bench
- ERPNext **v15 or v16** installed on the site (this app depends on ERPNext
  doctypes such as Customer, Territory, Sales Order, Quotation and
  Payment Entry)

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO
bench --site $SITE_NAME install-app sfa_crm
bench --site $SITE_NAME migrate
```

`[tool.bench.frappe-dependencies]` in `pyproject.toml` declares
`frappe = ">=15.0.0,<17.0.0"`, so `bench get-app` / Frappe Cloud correctly
match this app against both v15 and v16 benches. If you previously hit
`Could not find a compatible Frappe version in pyproject.toml`, pull the
latest `main` — this section was missing before and has since been added.

### Verified test steps

This app was tested end-to-end in a fresh Frappe v15 + ERPNext v15
bench:

1. `bench init --frappe-branch version-15`
2. `bench get-app erpnext --branch version-15` + `bench get-app <this repo>`
3. `bench install-app erpnext` then `bench install-app sfa_crm` — both complete
   with no errors
4. `bench migrate` — completes cleanly
5. App switcher (`/api/method/frappe.apps.get_apps`) correctly lists **SFA CRM**
   next to ERPNext
6. `/app/sfa-crm` workspace loads (HTTP 200)
7. Custom mobile endpoint `sfa_crm.api.get_api_token` returns a valid API
   key/secret pair for a logged-in user
8. Item's **Show in SFA App** checkbox is present and syncs correctly on a
   fresh v15 install (see note below)

### Item "Show in SFA App" not appearing on v15

Earlier installs on Frappe v15 could end up **missing the "Show in SFA App"
checkbox on Item**, even though the same install worked fine on v16. Root
cause: `sfa_crm/fixtures/custom_field.json` used to include a stray custom
field for `UTM Campaign` (a doctype that only exists on Frappe v16+, not on
v15). Frappe imports that file's records sequentially in one pass, so
hitting the missing `UTM Campaign` doctype partway through aborted the rest
of the file — including the `Item` field, which was listed after it.

Fixed by removing the unrelated `UTM Campaign` entry and giving `Item` its
own dedicated customization file (`sfa_crm/sfa_crm/custom/item.json`, synced
independently via `sync_on_migrate`), matching how `Customer` and
`Delivery Note` are already handled. If you installed before this fix,
run `bench --site $SITE_NAME migrate` after updating to the latest `main`
to pick up the field.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/sfa_crm
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs ERPNext + this app and runs unit tests against Frappe/ERPNext v15 on every push to `main`/`develop` and on every pull request.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
