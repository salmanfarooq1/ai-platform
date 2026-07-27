"""
Generate synthetic Enterprise Legal/Compliance corpus.
Three files — one per chunking strategy.
Domain: GDPR, data retention, breach reporting, employee policies.
"""
import json
from pathlib import Path

OUTPUT_DIR = Path("data/compliance")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── 1. Markdown → header_aware_split ──────────────────────────────────────────

GDPR_POLICY_MD = """# GDPR Compliance Policy

## Overview

This document outlines our organization's approach to compliance with the General
Data Protection Regulation (GDPR). All employees handling personal data must read
and understand this policy. Non-compliance may result in disciplinary action and
significant regulatory fines of up to €20 million or 4% of global annual turnover.

## Data Retention Policy

### Employee Records

Employee personal data must be retained for a minimum of 6 years following the
termination of employment. This includes contracts, payroll records, performance
reviews, and disciplinary records. After the retention period, data must be
securely deleted using approved methods such as cryptographic erasure or physical
destruction of storage media.

HR must maintain a data retention schedule and conduct annual audits to ensure
compliance. Any exceptions to standard retention periods must be approved in
writing by the Data Protection Officer (DPO).

### Customer Data

Customer personal data may only be retained for as long as necessary to fulfill
the purpose for which it was collected. For transactional data, the standard
retention period is 7 years to comply with financial regulations. Marketing data
must be deleted within 2 years of the last customer interaction unless explicit
consent for longer retention has been obtained.

### System Logs

Application and system logs containing personal data must not be retained for
more than 90 days. Security logs may be retained for up to 12 months with
appropriate access controls. Log retention policies must be reviewed quarterly.

## User Consent Requirements

### Lawful Basis for Processing

Under GDPR Article 6, all processing of personal data must have a lawful basis.
The six lawful bases are: consent, contract, legal obligation, vital interests,
public task, and legitimate interests. Organizations must document the lawful
basis for each processing activity in their Records of Processing Activities.

### Obtaining Valid Consent

Consent must be freely given, specific, informed, and unambiguous. Pre-ticked
boxes, silence, or inactivity do not constitute valid consent. Consent requests
must be separate from other terms and conditions. Users must be able to withdraw
consent as easily as they gave it.

Organizations must maintain records of when and how consent was obtained,
including what the user was told at the time of consent. Consent records must
be retained for the duration of processing plus 3 years.

### Children's Data

Processing personal data of children under 16 requires parental consent in most
EU member states. Age verification mechanisms must be implemented where services
are likely to be accessed by children. Extra safeguards apply to children's data
including enhanced security measures and prohibition on profiling.

## Data Breach Reporting

### Internal Reporting

Any employee who discovers or suspects a data breach must report it immediately
to their line manager and the Information Security team. Initial reports should
be made within 1 hour of discovery. The Information Security team will conduct
an initial assessment within 4 hours to determine the severity and scope.

A data breach includes any accidental or unlawful destruction, loss, alteration,
unauthorized disclosure of, or access to personal data. This includes lost
laptops, misdirected emails, unauthorized database access, and ransomware attacks.

### Regulatory Notification

Under GDPR Article 33, personal data breaches must be reported to the supervisory
authority within 72 hours of becoming aware of the breach, unless the breach is
unlikely to result in a risk to individuals. If notification is not made within
72 hours, a reasoned justification for the delay must be provided.

The notification must include the nature of the breach, categories and approximate
number of data subjects affected, likely consequences of the breach, and measures
taken or proposed to address the breach.

### Individual Notification

Under GDPR Article 34, when a breach is likely to result in a high risk to
individuals, those individuals must be notified without undue delay. The
communication must describe the nature of the breach in clear and plain language
and include contact details of the DPO, likely consequences, and measures taken.

## Data Subject Rights

### Right of Access

Data subjects have the right to obtain confirmation of whether their personal
data is being processed and access to that data. Requests must be responded to
within one calendar month. The response must include the purposes of processing,
categories of data, recipients, retention periods, and information about other
rights.

### Right to Erasure

Also known as the right to be forgotten, data subjects can request deletion of
their personal data when it is no longer necessary for the purpose it was
collected, consent is withdrawn, or the data has been unlawfully processed.
Erasure requests must be fulfilled within one month unless an exemption applies.

### Right to Data Portability

Data subjects have the right to receive their personal data in a structured,
commonly used, machine-readable format. This right applies to data processed
by automated means based on consent or contract. The data must be provided
within one month of the request.

## Third Party Data Processing

### Data Processing Agreements

Before engaging any third-party processor, a Data Processing Agreement (DPA)
must be in place. The DPA must include the subject matter, duration, nature
and purpose of processing, type of personal data, categories of data subjects,
and obligations and rights of the controller.

### International Data Transfers

Transfers of personal data outside the European Economic Area are only permitted
where adequate protections are in place. Approved mechanisms include adequacy
decisions, Standard Contractual Clauses, and Binding Corporate Rules. All
international transfers must be documented in the Records of Processing Activities.

## Article 5: Data Minimization Principle
Under GDPR Article 5, the data minimization principle dictates that personal data must be adequate, relevant, and limited to what is necessary in relation to the purposes for which they are processed. Our engineering teams must enforce this principle by never collecting extraneous fields from users.

## Legitimate Interest Assessment
Processing under legitimate interests requires a formal legitimate interest assessment (LIA) as guided by GDPR Recital 47. Recital 47 clarifies that the processing of personal data strictly necessary for the purposes of preventing fraud also constitutes a legitimate interest.

## CCPA Compliance
### CCPA Fines (Section 1798.155)
Under the California Consumer Privacy Act (CCPA), the attorney general can levy fines. Specifically, the maximum fine under CCPA section 1798.155 is $7,500 per intentional violation, and $2,500 per unintentional violation. 

## HIPAA Applicability
### Exempt Entities
It is critical to understand who is subject to the Health Insurance Portability and Accountability Act. Notably, HIPAA does NOT apply to entities such as life insurers, employers, workers compensation carriers, many schools and school districts, and many state agencies like child protective service agencies.
"""

# ── 2. Plain text → recursive_split ───────────────────────────────────────────

EMPLOYEE_HANDBOOK_TXT = """EMPLOYEE HANDBOOK — INFORMATION SECURITY AND DATA PROTECTION

SECTION 1: INTRODUCTION AND SCOPE

This handbook applies to all employees, contractors, consultants, and temporary
workers who have access to company information systems or personal data. Compliance
with the policies described in this handbook is a condition of employment. Violations
may result in disciplinary action up to and including termination and legal prosecution.

The organization is committed to protecting the personal data of employees, customers,
and business partners. We recognize that privacy is a fundamental right and that
responsible data stewardship is essential to maintaining trust.

SECTION 2: ACCEPTABLE USE OF INFORMATION SYSTEMS

All information systems, including computers, mobile devices, email, and cloud
services, are provided for business purposes. Limited personal use is permitted
provided it does not interfere with work duties, consume excessive resources, or
create legal or security risks for the organization.

Employees must not use company systems to access, store, or distribute material
that is illegal, offensive, or in violation of company policies. This includes
but is not limited to: pirated software, inappropriate content, or confidential
competitor information.

All activity on company systems may be monitored and recorded for security and
compliance purposes. Employees should have no expectation of privacy when using
company-provided systems or networks.

SECTION 3: PASSWORD AND ACCESS CONTROL POLICY

Passwords must be at least 14 characters long and contain a combination of
uppercase and lowercase letters, numbers, and special characters. Passwords
must not contain dictionary words, personal information, or sequences. Passwords
must be changed every 90 days and must not be reused for at least 12 cycles.

Multi-factor authentication is mandatory for all systems containing personal data
or classified information. Employees must not share passwords under any circumstances,
including with IT support staff. IT staff will never ask for your password.

Access to systems and data must follow the principle of least privilege. Employees
should only have access to data and systems necessary for their job function.
Access rights must be reviewed quarterly by department managers.

SECTION 4: HANDLING PERSONAL DATA

Personal data must only be collected for specified, explicit, and legitimate
purposes. It must not be processed in a manner incompatible with those purposes.
Employees must not collect more data than is necessary for the stated purpose.

Personal data must be kept accurate and up to date. Employees who become aware
of inaccurate personal data must correct it promptly or report it to the data
owner. Data subjects have the right to have inaccurate data corrected without
undue delay.

Personal data must be protected with appropriate technical and organizational
measures. This includes encryption of data at rest and in transit, access
controls, and regular security assessments. Sensitive personal data requires
additional protection measures.

SECTION 5: INCIDENT REPORTING PROCEDURES

All security incidents and suspected breaches must be reported immediately.
Do not attempt to investigate or resolve security incidents independently.
Contact the Information Security team via the dedicated incident hotline or
the security incident portal. In the event of ransomware or active attack,
disconnect your device from the network immediately before reporting.

A security incident includes: unauthorized access to systems or data, lost or
stolen devices containing company data, malware infections, phishing attempts
that may have been successful, and accidental disclosure of personal data to
unauthorized parties.

After reporting, preserve all evidence and do not delete files, emails, or
logs related to the incident. The Information Security team will provide
guidance on next steps. Full cooperation with incident investigation is required.

SECTION 6: REMOTE WORKING AND MOBILE DEVICE POLICY

Employees working remotely must use the company VPN for all access to internal
systems and data. Public WiFi networks must never be used without VPN protection.
Home networks should be secured with WPA3 encryption and a strong unique password.

Company laptops and mobile devices must have full disk encryption enabled at all
times. Devices must be locked when unattended, even at home. Screen lock must
activate after no more than 5 minutes of inactivity.

Personal devices may only be used for work purposes if enrolled in the Mobile
Device Management system and subject to company security policies. The organization
reserves the right to remotely wipe enrolled devices if they are lost or stolen
or if the employee leaves the organization.

SECTION 7: DATA CLASSIFICATION AND HANDLING

The organization uses four data classification levels. Public data may be freely
shared and requires no special handling. Internal data is for employee use only
and must not be shared externally without authorization. Confidential data
requires encryption in transit and at rest and may only be shared with authorized
parties under NDA. Restricted data includes personal data and trade secrets and
requires the highest level of protection including access logging.

Documents containing confidential or restricted data must be clearly labeled.
Physical documents must be stored in locked cabinets and shredded when no longer
needed. Electronic documents must be stored in approved secure locations and not
on local drives or personal cloud storage.

SECTION 8: THIRD PARTY AND VENDOR MANAGEMENT

All vendors and third parties with access to company data or systems must be
assessed for security and privacy compliance before engagement. The procurement
team must involve Information Security and Legal in vendor selection when data
access is required.

Vendor contracts must include appropriate data protection clauses, right to audit
provisions, and breach notification requirements. Vendors must be reassessed
annually and whenever there are material changes to their services or security posture.

SECTION 9: TRAINING AND AWARENESS

All employees must complete mandatory information security and data protection
training within 30 days of joining the organization. Annual refresher training
is required for all staff. Additional role-specific training is required for
employees handling sensitive personal data or with elevated system access.

Phishing simulation exercises are conducted quarterly. Employees who repeatedly
fail phishing simulations will be required to complete additional training.
Security awareness communications are sent monthly and must be read and acknowledged.

SECTION 10: DISCIPLINARY PROCEDURES

Violations of information security and data protection policies will be treated
seriously. Minor violations may result in additional training and a formal warning.
Serious violations including deliberate data breaches, sharing of credentials,
or unauthorized access to data will result in immediate suspension pending
investigation and may result in termination and referral to regulatory authorities.

Employees are encouraged to report policy violations by colleagues without fear
of retaliation. Reports may be made anonymously through the whistleblowing hotline.
All reports will be investigated promptly and confidentially.
"""

# ── 3. JSON → chunk_openapi_spec ──────────────────────────────────────────────

COMPLIANCE_API_JSON = {
    "openapi": "3.0.0",
    "info": {
        "title": "Compliance Management API",
        "version": "2.1.0",
        "description": "Internal API for managing compliance records, data subject requests, and incident reporting."
    },
    "paths": {
        "/api/v1/data-subject-requests": {
            "post": {
                "operationId": "createDataSubjectRequest",
                "summary": "Submit a new data subject request",
                "description": "Creates a GDPR data subject request (access, erasure, portability, or rectification). The request is assigned to the DPO queue and must be fulfilled within 30 days.",
                "tags": ["Data Subject Rights"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["request_type", "subject_email", "identity_verified"],
                                "properties": {
                                    "request_type": {"type": "string", "enum": ["access", "erasure", "portability", "rectification"]},
                                    "subject_email": {"type": "string", "format": "email"},
                                    "identity_verified": {"type": "boolean"},
                                    "additional_notes": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Request created successfully. Reference ID returned."},
                    "400": {"description": "Invalid request type or missing required fields."},
                    "422": {"description": "Identity verification required before processing."}
                }
            },
            "get": {
                "operationId": "listDataSubjectRequests",
                "summary": "List all pending data subject requests",
                "description": "Returns all open data subject requests. Requires DPO role. Results are paginated.",
                "tags": ["Data Subject Rights"],
                "parameters": [
                    {"name": "status", "in": "query", "required": False, "schema": {"type": "string", "enum": ["pending", "in_progress", "completed", "overdue"]}},
                    {"name": "page", "in": "query", "required": False, "schema": {"type": "integer", "default": 1}},
                    {"name": "page_size", "in": "query", "required": False, "schema": {"type": "integer", "default": 20}}
                ],
                "responses": {
                    "200": {"description": "List of data subject requests with pagination metadata."},
                    "403": {"description": "Insufficient permissions. DPO role required."}
                }
            }
        },
        "/api/v1/data-subject-requests/{request_id}": {
            "get": {
                "operationId": "getDataSubjectRequest",
                "summary": "Get details of a specific data subject request",
                "tags": ["Data Subject Rights"],
                "parameters": [
                    {"name": "request_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
                ],
                "responses": {
                    "200": {"description": "Full request details including timeline and assigned handler."},
                    "404": {"description": "Request not found."}
                }
            },
            "patch": {
                "operationId": "updateDataSubjectRequest",
                "summary": "Update status or add notes to a data subject request",
                "tags": ["Data Subject Rights"],
                "parameters": [
                    {"name": "request_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "status": {"type": "string", "enum": ["in_progress", "completed", "rejected"]},
                                    "handler_notes": {"type": "string"},
                                    "completion_evidence": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Request updated successfully."},
                    "404": {"description": "Request not found."},
                    "422": {"description": "Invalid status transition."}
                }
            }
        },
        "/api/v1/incidents": {
            "post": {
                "operationId": "reportSecurityIncident",
                "summary": "Report a new security incident or data breach",
                "description": "Creates a security incident record. If the incident involves personal data, GDPR breach notification workflow is automatically triggered. The 72-hour regulatory clock starts from incident creation time.",
                "tags": ["Incident Management"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["incident_type", "description", "discovery_timestamp", "involves_personal_data"],
                                "properties": {
                                    "incident_type": {"type": "string", "enum": ["data_breach", "unauthorized_access", "ransomware", "lost_device", "phishing", "other"]},
                                    "description": {"type": "string"},
                                    "discovery_timestamp": {"type": "string", "format": "date-time"},
                                    "involves_personal_data": {"type": "boolean"},
                                    "estimated_records_affected": {"type": "integer"},
                                    "affected_systems": {"type": "array", "items": {"type": "string"}}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Incident created. If personal data involved, breach notification workflow initiated."},
                    "400": {"description": "Missing required fields."},
                    "422": {"description": "Invalid incident type or timestamp format."}
                }
            },
            "get": {
                "operationId": "listIncidents",
                "summary": "List security incidents",
                "description": "Returns security incidents filtered by status, type, or date range. Requires Security Officer role.",
                "tags": ["Incident Management"],
                "parameters": [
                    {"name": "status", "in": "query", "required": False, "schema": {"type": "string", "enum": ["open", "investigating", "contained", "resolved", "reported_to_authority"]}},
                    {"name": "involves_personal_data", "in": "query", "required": False, "schema": {"type": "boolean"}},
                    {"name": "from_date", "in": "query", "required": False, "schema": {"type": "string", "format": "date"}},
                    {"name": "to_date", "in": "query", "required": False, "schema": {"type": "string", "format": "date"}}
                ],
                "responses": {
                    "200": {"description": "List of incidents with summary statistics."},
                    "403": {"description": "Security Officer role required."}
                }
            }
        },
        "/api/v1/incidents/{incident_id}/notify": {
            "post": {
                "operationId": "sendBreachNotification",
                "summary": "Send GDPR breach notification to supervisory authority",
                "description": "Submits formal breach notification. Must be called within 72 hours of breach discovery. Late notifications require a justification field. Generates audit trail entry.",
                "tags": ["Incident Management"],
                "parameters": [
                    {"name": "incident_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["authority_name", "notification_content", "data_categories", "approximate_subjects_affected"],
                                "properties": {
                                    "authority_name": {"type": "string"},
                                    "notification_content": {"type": "string"},
                                    "data_categories": {"type": "array", "items": {"type": "string"}},
                                    "approximate_subjects_affected": {"type": "integer"},
                                    "late_notification_justification": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Notification submitted. Reference number and timestamp returned."},
                    "400": {"description": "Missing required notification fields."},
                    "409": {"description": "Notification already submitted for this incident."},
                    "422": {"description": "Late notification requires justification field."}
                }
            }
        },
        "/api/v1/retention-policies": {
            "get": {
                "operationId": "listRetentionPolicies",
                "summary": "List all data retention policies",
                "description": "Returns all configured data retention policies by data category. Used by automated deletion jobs.",
                "tags": ["Data Retention"],
                "responses": {
                    "200": {"description": "List of retention policies with retention periods and deletion methods."},
                    "403": {"description": "DPO or Compliance Officer role required."}
                }
            },
            "post": {
                "operationId": "createRetentionPolicy",
                "summary": "Create a new data retention policy",
                "description": "Defines retention period and deletion method for a data category. Requires DPO approval workflow.",
                "tags": ["Data Retention"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["data_category", "retention_period_days", "deletion_method", "legal_basis"],
                                "properties": {
                                    "data_category": {"type": "string"},
                                    "retention_period_days": {"type": "integer"},
                                    "deletion_method": {"type": "string", "enum": ["cryptographic_erasure", "physical_destruction", "secure_overwrite", "anonymization"]},
                                    "legal_basis": {"type": "string"},
                                    "review_frequency_days": {"type": "integer", "default": 365}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Policy created. Pending DPO approval."},
                    "400": {"description": "Invalid deletion method or missing required fields."},
                    "409": {"description": "Policy for this data category already exists."}
                }
            }
        },
        "/api/v1/consent-records": {
            "post": {
                "operationId": "recordConsent",
                "summary": "Record user consent for data processing",
                "description": "Creates an immutable consent record. Consent records are append-only for audit purposes. Withdrawals are recorded as separate entries, not deletions.",
                "tags": ["Consent Management"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["subject_id", "processing_purpose", "consent_given", "consent_method"],
                                "properties": {
                                    "subject_id": {"type": "string"},
                                    "processing_purpose": {"type": "string"},
                                    "consent_given": {"type": "boolean"},
                                    "consent_method": {"type": "string", "enum": ["explicit_checkbox", "written_signature", "verbal_recorded", "opt_in_email"]},
                                    "consent_text_version": {"type": "string"},
                                    "ip_address": {"type": "string", "format": "ipv4"},
                                    "parent_guardian_id": {"type": "string", "description": "Required for subjects under 16"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "201": {"description": "Consent record created with timestamp and unique consent ID."},
                    "400": {"description": "Missing required fields or invalid consent method."},
                    "422": {"description": "Parent guardian ID required for minors."}
                }
            },
            "get": {
                "operationId": "getConsentHistory",
                "summary": "Get full consent history for a data subject",
                "description": "Returns complete consent audit trail for a subject, including all grants and withdrawals with timestamps.",
                "tags": ["Consent Management"],
                "parameters": [
                    {"name": "subject_id", "in": "query", "required": True, "schema": {"type": "string"}},
                    {"name": "purpose", "in": "query", "required": False, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {"description": "Full consent history with timestamps and consent text versions."},
                    "404": {"description": "No consent records found for this subject."}
                }
            }
        },
        "/api/v1/audit-log": {
            "get": {
                "operationId": "getAuditLog",
                "summary": "Query the compliance audit log",
                "description": "Returns tamper-evident audit log entries for compliance reporting. Supports filtering by actor, action type, and date range. Required for regulatory inspections.",
                "tags": ["Audit"],
                "parameters": [
                    {"name": "actor_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "action_type", "in": "query", "required": False, "schema": {"type": "string", "enum": ["data_access", "data_deletion", "consent_change", "breach_report", "policy_change"]}},
                    {"name": "from_date", "in": "query", "required": False, "schema": {"type": "string", "format": "date"}},
                    {"name": "to_date", "in": "query", "required": False, "schema": {"type": "string", "format": "date"}},
                    {"name": "page", "in": "query", "required": False, "schema": {"type": "integer", "default": 1}}
                ],
                "responses": {
                    "200": {"description": "Paginated audit log entries with cryptographic hash chain for tamper detection."},
                    "403": {"description": "Compliance Officer or DPO role required."}
                }
            }
        }
    }
}


def generate():
    # Write markdown
    md_path = OUTPUT_DIR / "gdpr_policy.md"
    md_path.write_text(GDPR_POLICY_MD, encoding="utf-8")
    print(f"[generated] {md_path} ({len(GDPR_POLICY_MD):,} chars)")

    # Write plain text
    txt_path = OUTPUT_DIR / "employee_handbook.txt"
    txt_path.write_text(EMPLOYEE_HANDBOOK_TXT, encoding="utf-8")
    print(f"[generated] {txt_path} ({len(EMPLOYEE_HANDBOOK_TXT):,} chars)")

    # Write JSON
    json_path = OUTPUT_DIR / "compliance_api.json"
    json_path.write_text(json.dumps(COMPLIANCE_API_JSON, indent=2), encoding="utf-8")
    print(f"[generated] {json_path} ({json_path.stat().st_size:,} bytes)")

    print(f"\nCorpus ready in {OUTPUT_DIR}/")
    print("Next: run scripts/ingest_compliance_corpus.py")


if __name__ == "__main__":
    generate()