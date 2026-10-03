export type AudienceSourceType = "manual" | "file" | "database";

export type JoinType = "LEFT JOIN" | "INNER JOIN";

export interface AudienceRecord {
  msisdn: string;
  /** Optional — language is never required */
  lang?: string | null;
  /** Where the record came from (auditing) */
  source: AudienceSourceType;
  /** Where the language came from */
  lang_source?: "input" | "reference" | null;
  mapping_status?: "Matched" | "No Match" | "Not applicable";
}

export interface ReferenceMappingConfig {
  enabled: boolean;
  connectionId: string;
  table: string;
  sourceJoinColumn: string;
  referenceJoinColumn: string;
  languageColumn: string;
  joinType: JoinType;
}

export const EMPTY_REFERENCE_CONFIG: ReferenceMappingConfig = {
  enabled: false,
  connectionId: "",
  table: "",
  sourceJoinColumn: "MSISDN",
  referenceJoinColumn: "",
  languageColumn: "",
  joinType: "LEFT JOIN",
};

/* ---------- MSISDN validation ---------- */

/** Accepts +2517xxxxxxxx, 2517xxxxxxxx, 07xxxxxxxx, 7xxxxxxxx (also 9xxxxxxxx) */
export function normalizeMsisdn(raw: string): string | null {
  const v = (raw || "").replace(/[\s()-]/g, "");
  if (!v) return null;
  let digits = v.startsWith("+") ? v.slice(1) : v;
  if (!/^\d+$/.test(digits)) return null;
  if (digits.startsWith("251")) {
    digits = digits.slice(3);
    if (/^70\d{8}$/.test(digits)) digits = `7${digits.slice(2)}`;
  }
  else if (digits.startsWith("0")) digits = digits.slice(1);
  if (!/^[79]\d{8}$/.test(digits)) return null;
  return `+251${digits}`;
}

export function isValidMsisdn(raw: string): boolean {
  return normalizeMsisdn(raw) !== null;
}
