export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes
    .filter((cls): cls is string => typeof cls === "string" && cls.length > 0)
    .join(" ");
}

type LocationLike = {
  country_name?: string | null;
  admin1?: string | null;
  admin2?: string | null;
  city?: string | null;
  district?: string | null;
  formatted_address?: string | null;
};

function uniqueParts(parts: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const part of parts) {
    const value = part?.trim();
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}

export function formatLocationSummary(
  location: LocationLike | null | undefined,
  options: { short?: boolean } = {},
): string | null {
  if (!location) return null;

  const omitCountry = location.country_name === "中国";
  const parts = options.short
    ? uniqueParts([
        location.city,
        location.district,
        location.admin1,
        omitCountry ? null : location.country_name,
      ])
    : uniqueParts([
        omitCountry ? null : location.country_name,
        location.admin1,
        location.admin2,
        location.city,
        location.district,
      ]);

  return parts.length > 0 ? parts.join(" · ") : null;
}

export function formatLocationAddress(location: LocationLike | null | undefined): string | null {
  if (!location) return null;
  const address = location.formatted_address?.trim();
  if (address) return address;
  return formatLocationSummary(location);
}
