"use client";

import { useEffect, useState } from "react";

import { FALLBACK_TIMEZONES } from "../constants";
import { timezoneOptions } from "../utils";

type TimezoneSelectProps = { id?: string; value: string; onChange: (timezone: string) => void };

// Reusable IANA timezone selector shared by company, agent, and coverage forms.
export function TimezoneSelect({ id, value, onChange }: TimezoneSelectProps) {
  const [zones, setZones] = useState(FALLBACK_TIMEZONES);

  useEffect(() => {
    if (typeof Intl.supportedValuesOf !== "function") return;
    setZones(["UTC", ...Intl.supportedValuesOf("timeZone").filter((zone) => zone !== "UTC")]);
  }, []);

  return (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      {timezoneOptions(zones, value).map((timezone) => <option key={timezone} value={timezone}>{timezone}</option>)}
    </select>
  );
}
