"use client";

import { DAYS } from "../constants";
import type { CoverageSegment, CoverageSummary, CoverageWindow } from "../types";
import { TimezoneSelect } from "./TimezoneSelect";
import type { Dispatch, SetStateAction } from "react";

type CoverageViewProps = {
  coverage: CoverageSummary | null;
  timezone: string;
  windows: CoverageWindow[];
  loading: boolean;
  saving: boolean;
  setTimezone: (timezone: string) => void;
  setWindows: Dispatch<SetStateAction<CoverageWindow[]>>;
  onSave: () => void;
};

// Edit required hours and display where agent schedules cover those hours.
export function CoverageView(props: CoverageViewProps) {
  const { coverage, timezone, windows, loading, saving, setTimezone, setWindows, onSave } = props;

  // Merge and sort covered intervals and gaps so the table reads in weekday order.
  const segments: CoverageSegment[] = coverage
    ? [...coverage.covered_periods, ...coverage.gaps].sort((a, b) =>
      a.day_of_week - b.day_of_week || a.start_time.localeCompare(b.start_time))
    : [];

  return (
    <>
      <section className="coverage-config">
        <div className="coverage-config-heading">
          <div><p className="eyebrow">WEEKLY REQUIREMENTS</p><h2>Required team coverage</h2><p>Set the periods when at least one agent should be available.</p></div>
          <button className="button primary" onClick={onSave} disabled={saving}>{saving ? "Saving…" : "Save coverage"}</button>
        </div>
        <label className="coverage-timezone">Company timezone
          <TimezoneSelect value={timezone} onChange={setTimezone} />
        </label>
        <div className="coverage-windows-heading">
          <h3>Required hours</h3>
          <button className="button secondary" onClick={() => setWindows((current) => [...current, { day_of_week: 0, start_time: "09:00", end_time: "17:00" }])}>+ Add hours</button>
        </div>
        {windows.length === 0 ? <p className="no-hours">No required coverage periods. Add hours to see coverage and gaps.</p> : <div className="window-list coverage-window-list">
          {windows.map((window, index) => <div className="window-row" key={`${window.id ?? "new"}-${index}`}>
            <label className="sr-only" htmlFor={`coverage-day-${index}`}>Coverage day</label>
            <select id={`coverage-day-${index}`} value={window.day_of_week} onChange={(event) => setWindows((current) => current.map((item, i) => i === index ? { ...item, day_of_week: Number(event.target.value) } : item))}>{DAYS.map((day, value) => <option value={value} key={day}>{day}</option>)}</select>
            <label className="sr-only" htmlFor={`coverage-start-${index}`}>Coverage start time</label>
            <input id={`coverage-start-${index}`} type="time" value={window.start_time} onChange={(event) => setWindows((current) => current.map((item, i) => i === index ? { ...item, start_time: event.target.value } : item))} />
            <span className="time-separator">to</span>
            <label className="sr-only" htmlFor={`coverage-end-${index}`}>Coverage end time</label>
            <input id={`coverage-end-${index}`} type="time" value={window.end_time} onChange={(event) => setWindows((current) => current.map((item, i) => i === index ? { ...item, end_time: event.target.value } : item))} />
            <button className="icon-button" title="Remove required hours" aria-label={`Remove ${DAYS[window.day_of_week]} coverage`} onClick={() => setWindows((current) => current.filter((_, i) => i !== index))}>×</button>
          </div>)}
        </div>}
      </section>

      <section className="coverage-results">
        <div className="section-heading">
          <div><h2>Team coverage</h2><p>Combined agent availability compared with required hours.</p></div>
          {coverage && <span className="count-pill">Week of {coverage.week_start}</span>}
        </div>
        {loading ? <div className="empty-state">Calculating weekly coverage…</div> : !coverage || coverage.required_windows.length === 0 ? (
          <div className="empty-state">Configure required hours to view covered periods and gaps.</div>
        ) : segments.length === 0 ? (
          <div className="empty-state">The selected week has no clock minutes in its configured coverage periods.</div>
        ) : <>
          <div className="coverage-timezone-note"><span>Company timezone</span><strong>{coverage.company_timezone}</strong></div>
          <div className="coverage-summary-cards">
            <div><span className="summary-value">{coverage.covered_periods.length}</span><span>covered periods</span></div>
            <div className={coverage.gaps.length ? "has-gaps" : ""}><span className="summary-value">{coverage.gaps.length}</span><span>coverage gaps</span></div>
          </div>
          <div className="coverage-segments" role="table" aria-label={`Team coverage in ${coverage.company_timezone}`}>
            <div className="coverage-segment coverage-segment-header" role="row">
              <span role="columnheader">Day</span><span role="columnheader">Time</span><span role="columnheader">Status</span>
            </div>
            {segments.map((segment, index) => <div className="coverage-segment" key={`${segment.day_of_week}-${segment.start_time}-${index}`}>
              <span className="coverage-day">{DAYS[segment.day_of_week]}</span>
              <span className="coverage-time">{segment.start_time} – {segment.end_time}</span>
              <span className={`coverage-state ${segment.covered ? "covered" : "gap"}`}>{segment.covered ? "Covered" : "Gap"}</span>
            </div>)}
          </div>
        </>}
        <footer className="footer-note">The summary uses the current company-local week and recurring schedules.</footer>
      </section>
    </>
  );
}
