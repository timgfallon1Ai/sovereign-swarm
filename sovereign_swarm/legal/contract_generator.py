"""Contract draft generation from templates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.legal.models import ContractDraft, ContractType

logger = structlog.get_logger()

# Contract templates with variable placeholders
_TEMPLATES: dict[ContractType, str] = {
    ContractType.SERVICE_AGREEMENT: """
SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of {effective_date}
by and between:

{provider_name} ("Provider")
and
{client_name} ("Client")

1. SERVICES
Provider agrees to provide the following services: {service_description}

2. TERM
This Agreement begins on {effective_date} and continues for {term_months} months
unless terminated earlier pursuant to the terms herein.

3. COMPENSATION
Client agrees to pay Provider {compensation} for the services described.
Payment terms: {payment_terms}

4. CONFIDENTIALITY
Both parties agree to maintain the confidentiality of any proprietary information
exchanged during the course of this engagement.

5. INTELLECTUAL PROPERTY
{ip_clause}

6. TERMINATION
Either party may terminate this Agreement with {notice_days} days written notice.

7. LIMITATION OF LIABILITY
{liability_clause}

8. GOVERNING LAW
This Agreement shall be governed by the laws of {governing_state}.

[REVIEW REQUIRED] This is a draft contract. Attorney review is required before execution.

____________________          ____________________
{provider_name}                {client_name}
Date: ____________            Date: ____________
""".strip(),
    ContractType.NDA: """
MUTUAL NON-DISCLOSURE AGREEMENT

This Mutual Non-Disclosure Agreement ("Agreement") is entered into as of {effective_date}
by and between:

{party_a} ("Party A")
and
{party_b} ("Party B")

1. DEFINITION OF CONFIDENTIAL INFORMATION
"Confidential Information" means any non-public information disclosed by either party,
including but not limited to: business plans, technical data, trade secrets,
financial information, customer lists, and product plans.

2. OBLIGATIONS
Each party agrees to:
(a) Hold Confidential Information in strict confidence
(b) Not disclose to any third party without prior written consent
(c) Use the information solely for the purpose of {purpose}

3. EXCLUSIONS
Confidential Information does not include information that:
(a) Is or becomes publicly available through no fault of the receiving party
(b) Was known to the receiving party prior to disclosure
(c) Is independently developed without use of Confidential Information
(d) Is rightfully received from a third party without restriction

4. TERM
This Agreement shall remain in effect for {term_years} years from the date of execution.

5. GOVERNING LAW
This Agreement shall be governed by the laws of {governing_state}.

[REVIEW REQUIRED] This is a draft NDA. Attorney review is required before execution.

____________________          ____________________
{party_a}                      {party_b}
Date: ____________            Date: ____________
""".strip(),
    ContractType.DPA: """
DATA PROCESSING AGREEMENT

This Data Processing Agreement ("DPA") is entered into as of {effective_date}
by and between:

{controller_name} ("Data Controller")
and
{processor_name} ("Data Processor")

1. SCOPE
This DPA applies to the processing of personal data as described in Annex A.

2. DATA PROCESSING DETAILS
- Categories of data subjects: {data_subjects}
- Types of personal data: {data_types}
- Purpose of processing: {processing_purpose}
- Duration: {duration}

3. PROCESSOR OBLIGATIONS
The Data Processor shall:
(a) Process personal data only on documented instructions from the Controller
(b) Ensure persons authorized to process data have committed to confidentiality
(c) Implement appropriate technical and organizational security measures
(d) Assist the Controller with data subject rights requests
(e) Delete or return all personal data at end of services

4. SUB-PROCESSORS
{sub_processor_clause}

5. DATA BREACH NOTIFICATION
Processor shall notify Controller without undue delay (within 72 hours) of any
personal data breach.

6. COMPLIANCE
This DPA is designed to comply with: {compliance_frameworks}

[REVIEW REQUIRED] This is a draft DPA. Attorney review is required before execution.
""".strip(),
    ContractType.EMPLOYMENT: """
EMPLOYMENT AGREEMENT

This Employment Agreement ("Agreement") is entered into as of {effective_date}
by and between:

{employer_name} ("Employer")
and
{employee_name} ("Employee")

1. POSITION AND DUTIES
Employee is hired for the position of {position}.
Duties include: {duties}

2. COMPENSATION
- Base salary: {salary}
- Payment frequency: {pay_frequency}
- Benefits: {benefits}

3. WORK SCHEDULE
{schedule}

4. AT-WILL EMPLOYMENT
Employment is at-will. Either party may terminate at any time with {notice_days} days notice.

5. CONFIDENTIALITY
Employee agrees to maintain confidentiality of all proprietary information.

6. NON-COMPETE
{non_compete_clause}

7. GOVERNING LAW
This Agreement shall be governed by the laws of {governing_state}.

[REVIEW REQUIRED] This is a draft agreement. Attorney review is required before execution.

____________________          ____________________
{employer_name}                {employee_name}
Date: ____________            Date: ____________
""".strip(),
}


class ContractGenerator:
    """Generate contract drafts from templates with variable substitution."""

    def generate(
        self,
        contract_type: ContractType,
        variables: dict[str, Any],
    ) -> ContractDraft:
        """Generate a contract draft from a template.

        Variables are substituted into the template. Missing variables
        are left as placeholders with [FILL IN] markers.
        """
        template = _TEMPLATES.get(contract_type)
        if not template:
            logger.warning("contract.no_template", type=contract_type.value)
            return ContractDraft(
                type=contract_type,
                full_text=f"[No template available for {contract_type.value}]",
                key_terms=variables,
            )

        # Set defaults
        variables.setdefault("effective_date", datetime.utcnow().strftime("%B %d, %Y"))
        variables.setdefault("governing_state", "Texas")

        # Substitute variables
        text = template
        for key, value in variables.items():
            text = text.replace(f"{{{key}}}", str(value))

        # Mark remaining placeholders
        import re

        remaining = re.findall(r"\{(\w+)\}", text)
        for placeholder in remaining:
            text = text.replace(f"{{{placeholder}}}", f"[FILL IN: {placeholder}]")

        parties = [
            v for k, v in variables.items()
            if any(term in k for term in ["name", "party"])
            and isinstance(v, str)
        ]

        return ContractDraft(
            type=contract_type,
            parties=parties,
            key_terms=variables,
            full_text=text,
            review_required=True,
        )

    @staticmethod
    def available_types() -> list[str]:
        """Return the contract types that have templates."""
        return [ct.value for ct in _TEMPLATES]
