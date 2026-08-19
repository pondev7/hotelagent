/**
 * Turning API values into things a human reads.
 *
 * Kept out of the components so that "how we show a commission" is one
 * decision in one place, and so it can be tested without rendering anything.
 */

/**
 * A commission rate, as a percentage.
 *
 * `rate` arrives as a **string** — the API sends `Numeric(5,2)` that way
 * deliberately, because JavaScript's `number` is a float and `0.1 + 0.2` is not
 * `0.3`. So this formats the digits rather than doing arithmetic on them: the
 * value is never parsed, only trimmed and suffixed. The moment anyone needs to
 * *add* two of these, the answer is a decimal library, not `parseFloat`.
 */
export function formatCommission(rate: string): string {
  const trimmed = rate.includes(".") ? rate.replace(/0+$/, "").replace(/\.$/, "") : rate;
  return `${trimmed}%`;
}

/**
 * A phone number, partially masked.
 *
 * `CLAUDE.md` bans full phone numbers from logs. A screen is not a log — an
 * operator about to telephone reception needs the whole number — so this is
 * used for the list, where the number is context rather than an instruction,
 * and the detail view shows it in full.
 */
export function maskPhone(phone: string | null | undefined): string {
  if (!phone) return "—";
  return phone.length <= 4 ? phone : `${phone.slice(0, -4).replace(/\d/g, "•")}${phone.slice(-4)}`;
}
