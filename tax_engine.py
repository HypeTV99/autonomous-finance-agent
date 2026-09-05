from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import logging
import re
from typing import Any, Dict, Optional, Union
from schemas import CanonicalTDSRule, TaxCalculationResult, TaxFramework, TDSSection

logger = logging.getLogger("TaxEngine")


class StatutoryComplianceTaxEngine:
    TDS_RATES: Dict[TDSSection, Decimal] = {
        TDSSection.SECTION_194C_INDIVIDUAL: Decimal("0.01"),  # 1%
        TDSSection.SECTION_194C_COMPANY: Decimal("0.02"),     # 2%
        TDSSection.SECTION_194J_TECH: Decimal("0.02"),        # 2%
        TDSSection.SECTION_194J_PROF: Decimal("0.10"),        # 10%
        TDSSection.SECTION_194Q_GOODS: Decimal("0.001"),      # 0.1%
        TDSSection.NONE: Decimal("0.00"),
    }
    PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
    TRANSITION_CUTOFF = date(2026, 3, 31)
    SECTION_206AB_OMISSION_DATE = date(2025, 4, 1)

    @classmethod
    def parse_statutory_date(cls, raw_dt: Any) -> Optional[date]:
        if not raw_dt:
            return None
        if isinstance(raw_dt, date):
            return raw_dt
        if isinstance(raw_dt, datetime):
            return raw_dt.date()
        
        s = str(raw_dt).strip()
        # 1. ISO format: YYYY-MM-DD
        iso_match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
        if iso_match:
            try:
                return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            except ValueError:
                pass

        # 2. Indian/UK format: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        dmy_match = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
        if dmy_match:
            try:
                return date(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
            except ValueError:
                pass

        # 3. Textual month format: DD-Mon-YYYY (e.g. 31-Mar-2026 or 31 March 2026)
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
        }
        txt_match = re.match(r"^(\d{1,2})[-/\s]+([A-Za-z]+)[-/\s]+(\d{4})", s)
        if txt_match:
            day, m_str, year = int(txt_match.group(1)), txt_match.group(2).lower(), int(txt_match.group(3))
            m_num = months.get(m_str) or months.get(m_str[:3])
            if m_num:
                try:
                    return date(year, m_num, day)
                except ValueError:
                    pass

        return None

    @classmethod
    def resolve_statutory_framework(
        cls, section: TDSSection, tx_date: Optional[date] = None, vendor_pan: str = ""
    ) -> Dict[str, Any]:
        dt = tx_date or date.today()
        is_legacy_1961 = (dt <= cls.TRANSITION_CUTOFF)

        framework = TaxFramework.INCOME_TAX_ACT_1961 if is_legacy_1961 else TaxFramework.INCOME_TAX_ACT_2025

        if section in (TDSSection.SECTION_194C_INDIVIDUAL, TDSSection.SECTION_194C_IND):
            canonical = CanonicalTDSRule.TDS_CONTRACTOR_INDIVIDUAL
            provision = "Income-tax Act, 1961 - Section 194C(1)" if is_legacy_1961 else "Income-tax Act, 2025 - Section 393(1) Table Item 2(a)"
            gov_sec = "194C(1)" if is_legacy_1961 else "393(1)"
            gov_item = "Individual/HUF" if is_legacy_1961 else "Table Item 2(a)"
            internal_rule = "RULE-ITA1961-194C1" if is_legacy_1961 else "RULE-ITA2025-393-2A"
            return_form = "Form 26Q"
            return_field = "94C"
            internal_code = "94C" if is_legacy_1961 else "393-2A"
            challan_code = "94C"
        elif section in (TDSSection.SECTION_194C_COMPANY, TDSSection.SECTION_194C_CORP):
            canonical = CanonicalTDSRule.TDS_CONTRACTOR_COMPANY
            provision = "Income-tax Act, 1961 - Section 194C(2)" if is_legacy_1961 else "Income-tax Act, 2025 - Section 393(1) Table Item 2(b)"
            gov_sec = "194C(2)" if is_legacy_1961 else "393(1)"
            gov_item = "Company/Other" if is_legacy_1961 else "Table Item 2(b)"
            internal_rule = "RULE-ITA1961-194C2" if is_legacy_1961 else "RULE-ITA2025-393-2B"
            return_form = "Form 26Q"
            return_field = "94C"
            internal_code = "94C" if is_legacy_1961 else "393-2B"
            challan_code = "94C"
        elif section == TDSSection.SECTION_194J_TECH:
            canonical = CanonicalTDSRule.TDS_TECHNICAL_SERVICES
            provision = "Income-tax Act, 1961 - Section 194J(1)(ba)" if is_legacy_1961 else "Income-tax Act, 2025 - Section 393(1) Table Item 7(a)"
            gov_sec = "194J(1)(ba)" if is_legacy_1961 else "393(1)"
            gov_item = "Technical Services" if is_legacy_1961 else "Table Item 7(a)"
            internal_rule = "RULE-ITA1961-194J-TECH" if is_legacy_1961 else "RULE-ITA2025-393-7A"
            return_form = "Form 26Q"
            return_field = "94J"
            internal_code = "94J-TECH" if is_legacy_1961 else "393-7A"
            challan_code = "94J"
        elif section == TDSSection.SECTION_194J_PROF:
            canonical = CanonicalTDSRule.TDS_PROFESSIONAL_SERVICES
            provision = "Income-tax Act, 1961 - Section 194J(1)(h)" if is_legacy_1961 else "Income-tax Act, 2025 - Section 393(1) Table Item 7(b)"
            gov_sec = "194J(1)(h)" if is_legacy_1961 else "393(1)"
            gov_item = "Professional Services" if is_legacy_1961 else "Table Item 7(b)"
            internal_rule = "RULE-ITA1961-194J-PROF" if is_legacy_1961 else "RULE-ITA2025-393-7B"
            return_form = "Form 26Q"
            return_field = "94J"
            internal_code = "94J-PROF" if is_legacy_1961 else "393-7B"
            challan_code = "94J"
        elif section in (TDSSection.SECTION_194Q_GOODS, TDSSection.SECTION_194Q):
            canonical = CanonicalTDSRule.TDS_PURCHASE_OF_GOODS
            provision = "Income-tax Act, 1961 - Section 194Q" if is_legacy_1961 else "Income-tax Act, 2025 - Section 393(1) Table Item 14"
            gov_sec = "194Q" if is_legacy_1961 else "393(1)"
            gov_item = "Purchase of Goods" if is_legacy_1961 else "Table Item 14"
            internal_rule = "RULE-ITA1961-194Q" if is_legacy_1961 else "RULE-ITA2025-393-14"
            return_form = "Form 26Q"
            return_field = "94Q"
            internal_code = "94Q" if is_legacy_1961 else "393-14"
            challan_code = "94Q"
        elif section == TDSSection.SECTION_197_LOWER:
            canonical = CanonicalTDSRule.TDS_LOWER_CERTIFICATE
            provision = "Income-tax Act, 1961 - Section 197" if is_legacy_1961 else "Income-tax Act, 2025 - Section 395(1)"
            gov_sec = "197" if is_legacy_1961 else "395(1)"
            gov_item = "Lower/Nil Deduction Certificate"
            internal_rule = "RULE-ITA1961-197" if is_legacy_1961 else "RULE-ITA2025-395-1"
            return_form = "Form 26Q"
            return_field = "197"
            internal_code = "197-CERT" if is_legacy_1961 else "395-CERT"
            challan_code = "197"
        else:
            canonical = CanonicalTDSRule.NONE
            provision = "Exempt / Below Threshold"
            gov_sec = "EXEMPT"
            gov_item = "Below Threshold"
            internal_rule = "RULE-EXEMPT"
            return_form = "Form 26Q"
            return_field = "EXEMPT"
            internal_code = "EXEMPT"
            challan_code = "NONE"

        if is_legacy_1961:
            gazette = "Income-tax Act, 1961 (Act No. 43 of 1961)"
            cbdt_ref = "CBDT Circular No. 23/2017"
            source_uri = "https://incometaxindia.gov.in/pages/acts/income-tax-act-1961.aspx"
        else:
            gazette = "Income-tax Act, 2025 (Act No. 4 of 2025)"
            cbdt_ref = "CBDT Circular No. 23/2017 & CBDT Notification No. 12/2026"
            source_uri = "https://incometaxindia.gov.in/pages/acts/income-tax-act-2025.aspx"

        return {
            "internal_rule_id": internal_rule,
            "tax_framework": framework,
            "canonical_rule_id": canonical,
            "statutory_provision": provision,
            "government_section": gov_sec,
            "government_table_item": gov_item,
            "gazette_citation": gazette,
            "cbdt_circular_reference": cbdt_ref,
            "official_source_uri": source_uri,
            "effective_date": dt.isoformat(),
            "rule_version": "v1961.Legacy" if is_legacy_1961 else "v2025.1-ITA2025-Transition",
            "policy_version": "2026.1",
            "statutory_return_form": return_form,
            "statutory_return_field_code": return_field,
            "form_26q_code": return_field,
            "internal_reporting_code": internal_code,
            "challan_281_code": challan_code,
            "pan_26as_credit_tag": f"26AS-{vendor_pan}-{dt.year}" if vendor_pan else None,
            "calculation_version": "v2.0-DualAct-DateAware"
        }

    @classmethod
    def validate_pan_format(cls, pan: str) -> bool:
        return bool(cls.PAN_REGEX.match(pan.strip().upper()))

    @classmethod
    def compute_statutory_tax(
        cls,
        subtotal_excluding_gst: Optional[Decimal] = None,
        gst_amount: Decimal = Decimal("0.00"),
        nominated_section: TDSSection = TDSSection.NONE,
        vendor_pan: str = "",
        is_pan_valid: Optional[bool] = None,
        is_pan_inoperative: bool = False,
        is_206ab_non_filer: bool = False,
        sec_197_cert: Optional[Dict[str, Any]] = None,
        ytd_billing: Decimal = Decimal("0.00"),
        transaction_date: Optional[Union[str, date]] = None,
        # Backward-compatible keyword normalization
        subtotal: Optional[Decimal] = None,
        section: Optional[TDSSection] = None,
        is_206ab_specified_person: Optional[bool] = None,
        ytd_vendor_billing: Optional[Decimal] = None,
        ytd_goods_purchase_billing: Optional[Decimal] = None,
        ytd_contractor_billing: Optional[Decimal] = None,
        invoice_date: Optional[str] = None,
        **kwargs
    ) -> TaxCalculationResult:
        base_subtotal = subtotal_excluding_gst if subtotal_excluding_gst is not None else subtotal
        if base_subtotal is None:
            raise ValueError("Missing required invoice subtotal amount.")

        # Seamless alias support for GST/tax amount
        effective_gst = gst_amount if gst_amount != Decimal("0.00") else kwargs.get("tax_amount", Decimal("0.00"))

        active_section = nominated_section if nominated_section != TDSSection.NONE else (section or TDSSection.NONE)
        non_filer_flag = is_206ab_non_filer or (is_206ab_specified_person is True)
        
        cumulative_ytd = ytd_billing
        if cumulative_ytd == Decimal("0.00"):
            cumulative_ytd = ytd_vendor_billing or ytd_goods_purchase_billing or ytd_contractor_billing or Decimal("0.00")

        effective_pan = vendor_pan or kwargs.get("pan", "")
        if is_pan_valid is None:
            is_pan_valid = cls.validate_pan_format(effective_pan)

        taxable_subject_to_tds = base_subtotal
        is_threshold_breached = True

        # Phase 1: Statutory Threshold Priority Evaluation
        if active_section in (TDSSection.SECTION_194C_INDIVIDUAL, TDSSection.SECTION_194C_COMPANY):
            single_breach = base_subtotal >= Decimal("30000.00")
            aggregate_breach = (cumulative_ytd + base_subtotal) >= Decimal("100000.00")
            if not single_breach and not aggregate_breach:
                is_threshold_breached = False
                active_section = TDSSection.NONE
                taxable_subject_to_tds = Decimal("0.00")

        elif active_section in (TDSSection.SECTION_194J_TECH, TDSSection.SECTION_194J_PROF):
            single_breach = base_subtotal >= Decimal("30000.00")
            aggregate_breach = (cumulative_ytd + base_subtotal) >= Decimal("30000.00")
            if not single_breach and not aggregate_breach:
                is_threshold_breached = False
                active_section = TDSSection.NONE
                taxable_subject_to_tds = Decimal("0.00")

        elif active_section == TDSSection.SECTION_194Q_GOODS:
            statutory_limit = Decimal("5000000.00")
            cumulative_purchase = cumulative_ytd + base_subtotal
            if cumulative_purchase <= statutory_limit:
                is_threshold_breached = False
                active_section = TDSSection.NONE
                taxable_subject_to_tds = Decimal("0.00")
            else:
                if cumulative_ytd >= statutory_limit:
                    taxable_subject_to_tds = base_subtotal
                else:
                    taxable_subject_to_tds = cumulative_purchase - statutory_limit

        raw_dt = transaction_date or invoice_date or kwargs.get("date")
        parsed_date = cls.parse_statutory_date(raw_dt)
        statutory_meta = cls.resolve_statutory_framework(active_section, parsed_date, vendor_pan=effective_pan)

        # If below exemption threshold -> Exempt from TDS
        if not is_threshold_breached or active_section == TDSSection.NONE:
            net_base = base_subtotal
            final_payout = (net_base + effective_gst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return TaxCalculationResult(
                applied_section=TDSSection.NONE,
                taxable_base=base_subtotal,
                taxable_amount_subject_to_tds=Decimal("0.00"),
                tds_rate=Decimal("0.00"),
                tds_deducted=Decimal("0.00"),
                net_base_payable=net_base,
                gst_payable=effective_gst,
                final_disbursement=final_payout,
                is_penal_rate_applied=False,
                **statutory_meta
            )

        # Phase 2: Section 206AA (Invalid/Inoperative PAN) & Section 206AB (Non-Filer, omitted post-1-Apr-2025)
        is_206ab_applicable = True
        if parsed_date and parsed_date >= cls.SECTION_206AB_OMISSION_DATE:
            # Section 206AB omitted with effect from 1 April 2025 (Finance Act 2025)
            is_206ab_applicable = False

        effective_non_filer = non_filer_flag if is_206ab_applicable else False
        has_penal_condition = (not is_pan_valid) or is_pan_inoperative or effective_non_filer
        if has_penal_condition:
            penal_rate = Decimal("0.05") if active_section == TDSSection.SECTION_194Q_GOODS else Decimal("0.20")
            tds_deducted = (taxable_subject_to_tds * penal_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_base = base_subtotal - tds_deducted
            final_payout = (net_base + effective_gst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            return TaxCalculationResult(
                applied_section=active_section,
                taxable_base=base_subtotal,
                taxable_amount_subject_to_tds=taxable_subject_to_tds,
                tds_rate=penal_rate,
                tds_deducted=tds_deducted,
                net_base_payable=net_base,
                gst_payable=effective_gst,
                final_disbursement=final_payout,
                is_penal_rate_applied=True,
                **statutory_meta
            )

        # Phase 3: Section 197 / Section 395(1) Lower Deduction Certificate (Hardened)
        is_cert_valid = False
        if sec_197_cert and sec_197_cert.get("is_active", False):
            cert_from = cls.parse_statutory_date(sec_197_cert.get("valid_from"))
            cert_to = cls.parse_statutory_date(sec_197_cert.get("valid_to"))
            
            date_ok = True
            if parsed_date:
                if cert_from and parsed_date < cert_from:
                    date_ok = False
                if cert_to and parsed_date > cert_to:
                    date_ok = False
            
            cert_sec = sec_197_cert.get("section")
            sec_ok = True
            if cert_sec and str(cert_sec).upper() not in (active_section.value, active_section.name, "ALL"):
                sec_ok = False
            
            if date_ok and sec_ok:
                is_cert_valid = True

        if is_cert_valid:
            raw_rate = sec_197_cert.get("rate") or sec_197_cert.get("concessional_rate") or sec_197_cert.get("concessional_rate_percentage", Decimal("0.00"))
            lower_rate = Decimal(str(raw_rate))
            if lower_rate > Decimal("1.0"):
                lower_rate = lower_rate / Decimal("100.0")  # Normalize e.g. 0.5% -> 0.005
            tds_deducted = (taxable_subject_to_tds * lower_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_base = base_subtotal - tds_deducted
            final_payout = (net_base + effective_gst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            lower_meta = cls.resolve_statutory_framework(TDSSection.SECTION_197_LOWER, parsed_date, vendor_pan=effective_pan)
            return TaxCalculationResult(
                applied_section=TDSSection.SECTION_197_LOWER,
                taxable_base=base_subtotal,
                taxable_amount_subject_to_tds=taxable_subject_to_tds,
                tds_rate=lower_rate,
                tds_deducted=tds_deducted,
                net_base_payable=net_base,
                gst_payable=effective_gst,
                final_disbursement=final_payout,
                is_penal_rate_applied=False,
                **lower_meta
            )

        # Phase 4: Standard Statutory Rates
        rate = cls.TDS_RATES[active_section]
        tds_deducted = (taxable_subject_to_tds * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_base = base_subtotal - tds_deducted
        final_payout = (net_base + effective_gst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return TaxCalculationResult(
            applied_section=active_section,
            taxable_base=base_subtotal,
            taxable_amount_subject_to_tds=taxable_subject_to_tds,
            tds_rate=rate,
            tds_deducted=tds_deducted,
            net_base_payable=net_base,
            gst_payable=effective_gst,
            final_disbursement=final_payout,
            is_penal_rate_applied=False,
            **statutory_meta
        )
