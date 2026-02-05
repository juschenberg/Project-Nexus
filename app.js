const btnSourceTop = document.getElementById('btn-source-top');
const meta = document.getElementById('input-meta');
const schedule = document.getElementById('schedule');
const statusLog = document.getElementById('status-log');
const apiMeta = document.getElementById('api-meta');

const kpiEmployees = document.getElementById('kpi-employees');
const kpiShifts = document.getElementById('kpi-shifts');
const kpiConflicts = document.getElementById('kpi-conflicts');

const btnDemo = document.getElementById('btn-demo');
const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');

const REQUIRED_SHEETS = ['PARAMS', 'EMPLOYEES', 'SHIFTS', 'ABSENCES', 'ASSIGNMENTS'];
const DAY_KEYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DEFAULT_SOURCE = 'data/Baeckerei_Workflow_Input.xlsx';
const API_URL = 'http://127.0.0.1:5000/api/preferences';
const API_TOKEN = ''; // optional: Bearer Token

if (apiMeta) {
  apiMeta.textContent = API_URL ? `API verbunden: ${API_URL}` : 'API: nicht konfiguriert';
}

btnSourceTop.addEventListener('click', () => loadFromSource(DEFAULT_SOURCE));

btnDemo.addEventListener('click', () => {
  const demo = buildDemoPlan();
  renderPlan(demo);
  meta.textContent = 'Demo-Daten geladen.';
  logStatus('Demo-Daten gerendert.');
});

tabButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.tab;
    tabButtons.forEach(b => b.classList.toggle('active', b === btn));
    tabPanels.forEach(panel => {
      panel.classList.toggle('active', panel.id === `tab-${target}`);
    });
  });
});

async function loadFromSource(path) {
  meta.textContent = `Lade Datei: ${path}`;
  clearStatus();
  logStatus('Starte Ladevorgang.');
  try {
    logStatus('Prüfe XLSX-Library...');
    await ensureXlsxLoaded();
    logStatus('XLSX-Library geladen.');
  } catch (err) {
    meta.textContent = 'Fehler: XLSX-Library nicht geladen. Prüfe Internetzugang oder lade die Seite neu.';
    logStatus('XLSX-Library konnte nicht geladen werden.');
    return;
  }

  try {
    logStatus('Lade Excel-Datei über fetch...');
    const response = await fetch(path);
    if (!response.ok) {
      meta.textContent = `Fehler beim Laden: ${response.status} ${response.statusText}`;
      logStatus(`HTTP Fehler: ${response.status}`);
      clearPlan();
      return;
    }
    logStatus('Datei geladen. Lese ArrayBuffer...');
    const buffer = await response.arrayBuffer();
    logStatus('Excel wird geparst...');
    const workbook = XLSX.read(buffer, { type: 'array' });

    const missing = REQUIRED_SHEETS.filter(s => !workbook.SheetNames.includes(s));
    if (missing.length) {
      meta.textContent = `Fehlende Sheets: ${missing.join(', ')}`;
      logStatus(`Fehlende Sheets: ${missing.join(', ')}`);
      clearPlan();
      return;
    }

    const data = parseWorkbook(workbook);
    const preferences = await fetchPreferences();
    data.preferences = preferences;
    if (preferences.length) {
      logStatus(`API Preferences geladen: ${preferences.length}`);
    }
    const plan = generatePlan(data);
    renderPlan(plan);
    meta.textContent = `Plan erstellt für ${formatDate(plan.startDate)} bis ${formatDate(plan.endDate)}.`;
    logStatus('Plan erfolgreich gerendert.');
  } catch (err) {
    meta.textContent = 'Fehler: Datei konnte nicht geladen werden.';
    logStatus(`Fehler: ${err?.message || 'unbekannt'}`);
    clearPlan();
  }
}

function ensureXlsxLoaded() {
  if (typeof XLSX !== 'undefined') return Promise.resolve(true);

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('xlsx load timeout'));
    }, 8000);

    const existing = document.querySelector('script[data-xlsx-loader]');
    if (existing) {
      existing.addEventListener('load', () => {
        clearTimeout(timeout);
        resolve(true);
      }, { once: true });
      existing.addEventListener('error', () => {
        clearTimeout(timeout);
        reject(new Error('xlsx load failed'));
      }, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = 'vendor/xlsx.full.min.js';
    script.async = true;
    script.dataset.xlsxLoader = 'true';
    script.onload = () => {
      clearTimeout(timeout);
      resolve(true);
    };
    script.onerror = () => {
      clearTimeout(timeout);
      reject(new Error('xlsx load failed'));
    };
    document.head.appendChild(script);
  });
}

async function fetchPreferences() {
  if (!API_URL) {
    logStatus('API nicht konfiguriert, überspringe Preferences.');
    return [];
  }

  try {
    logStatus('Hole Preferences von API...');
    const headers = API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {};
    const res = await fetch(API_URL, { headers });
    if (!res.ok) {
      logStatus(`API Fehler: ${res.status} ${res.statusText}`);
      return [];
    }
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    logStatus(`API Fehler: ${err?.message || 'unbekannt'}`);
    return [];
  }
}

function logStatus(message) {
  if (!statusLog) return;
  const line = document.createElement('div');
  line.textContent = `• ${message}`;
  statusLog.appendChild(line);
}

function clearStatus() {
  if (!statusLog) return;
  statusLog.innerHTML = '';
}

function parseWorkbook(workbook) {
  const params = sheetToObjects(workbook.Sheets.PARAMS);
  const employees = sheetToObjects(workbook.Sheets.EMPLOYEES);
  const shifts = sheetToObjects(workbook.Sheets.SHIFTS);
  const absences = sheetToObjects(workbook.Sheets.ABSENCES);

  const paramMap = {};
  for (const row of params) {
    if (row.Parameter) paramMap[row.Parameter] = row.Value;
  }

  return { params: paramMap, employees, shifts, absences };
}

function sheetToObjects(sheet) {
  return XLSX.utils.sheet_to_json(sheet, {
    defval: '',
    raw: true
  });
}

function generatePlan(data) {
  const startDate = resolveStartDate(data);
  const days = 7;

  const dates = [];
  for (let i = 0; i < days; i += 1) {
    const d = new Date(startDate);
    d.setDate(d.getDate() + i);
    dates.push(d);
  }

  const employees = data.employees.map(normalizeEmployee);
  applyPreferences(employees, data.preferences || []);
  const shifts = data.shifts.map(normalizeShift);

  const assignedHours = Object.fromEntries(employees.map(e => [e.id, 0]));
  const assignedByDate = {};
  let conflicts = 0;

  let totalShiftInstances = 0;
  const dayPlans = dates.map(date => {
    const dayKey = DAY_KEYS[date.getDay() === 0 ? 6 : date.getDay() - 1];
    const dayShifts = shifts.filter(s => s.dayOfWeek === dayKey);
    totalShiftInstances += dayShifts.length;
    const planned = dayShifts.map(shift => {
      const assigned = [];
      const eligible = employees.filter(emp => isEligible(emp, shift, dayKey, date, assignedByDate, assignedHours));
      eligible.sort((a, b) => {
        if (a.weeklyHours !== b.weeklyHours) return a.weeklyHours - b.weeklyHours;
        return a.name.localeCompare(b.name);
      });

      for (let i = 0; i < shift.required; i += 1) {
        const pick = eligible.find(e => !assigned.includes(e.id));
        if (!pick) {
          conflicts += 1;
          break;
        }
        assignEmployee(pick, shift, date, assigned, assignedByDate, assignedHours);
      }

      return {
        shift,
        assigned: assigned.map(id => employees.find(e => e.id === id)?.name || id)
      };
    });

    return {
      date,
      label: `${dayKey} ${formatDateShort(date)}`,
      shifts: planned
    };
  });

  return {
    startDate: dates[0],
    endDate: dates[dates.length - 1],
    employees,
    shifts,
    totalShiftInstances,
    conflicts,
    days: dayPlans
  };
}

function normalizeEmployee(row) {
  const qualifications = {};
  Object.keys(row).forEach(key => {
    if (key.startsWith('Qualified_')) {
      const role = key.replace('Qualified_', '');
      qualifications[role] = String(row[key]).trim() === '1' || row[key] === 1;
    }
  });

  const availability = {};
  DAY_KEYS.forEach(day => {
    availability[day] = {
      earliest: toNumber(row[`${day}_Earliest`]),
      latest: toNumber(row[`${day}_Latest`])
    };
  });

  return {
    id: row.EmployeeID,
    name: row.Name,
    contract: row.ContractType,
    weeklyTarget: toNumber(row.WeeklyHoursTarget),
    maxPerDay: toNumber(row.MaxHoursPerDay),
    canWorkSun: String(row.CanWorkSun) === '1' || row.CanWorkSun === 1,
    preferredPattern: row.PreferredPattern || '',
    hourlyCost: toNumber(row.HourlyCostEUR),
    qualifications,
    availability,
    weeklyHours: 0
  };
}

function normalizeShift(row) {
  const start = toNumber(row.StartTime);
  const end = toNumber(row.EndTime);
  const hours = toNumber(row.ShiftHours) || Math.max(0, (end - start) * 24);
  return {
    id: row.ShiftTemplateID,
    dayOfWeek: row.DayOfWeek,
    department: row.Department,
    position: row.Position,
    start,
    end,
    required: Math.max(1, Number(row.RequiredHeadcount || 1)),
    hours
  };
}

function applyPreferences(employees, preferences) {
  if (!preferences.length) return;

  const byId = Object.fromEntries(employees.map(e => [String(e.id), e]));
  const byName = Object.fromEntries(employees.map(e => [String(e.name).toLowerCase(), e]));

  preferences.forEach(pref => {
    const idKey = String(pref.employee_id || '');
    const nameKey = String(pref.name || '').toLowerCase();
    const emp = byId[idKey] || byName[nameKey];
    if (!emp) return;

    if (pref.weekly_hours != null) emp.weeklyTarget = Number(pref.weekly_hours);
    if (pref.max_hours_per_day != null) emp.maxPerDay = Number(pref.max_hours_per_day);
    if (pref.can_work_sun != null) emp.canWorkSun = !!pref.can_work_sun;
    if (pref.hourly_salary != null) emp.hourlyCost = Number(pref.hourly_salary);
    if (pref.contract_type) emp.contract = pref.contract_type;

    if (pref.slots && typeof pref.slots === 'object') {
      Object.entries(pref.slots).forEach(([dayLabel, slot]) => {
        const dayKey = mapDayLabel(dayLabel);
        if (!dayKey) return;
        const window = slotToWindow(slot);
        emp.availability[dayKey] = window;
      });
    }
  });
}

function isEligible(emp, shift, dayKey, date, assignedByDate, assignedHours) {
  if (dayKey === 'Sun' && !emp.canWorkSun) return false;
  if (!emp.qualifications[shift.position]) return false;
  if (!isAvailable(emp, dayKey, shift.start, shift.end)) return false;
  if (isOverlapping(emp, date, shift, assignedByDate)) return false;

  const maxPerDay = emp.maxPerDay || 24;
  const dayKeyIso = date.toISOString().slice(0, 10);
  const currentDayHours = assignedByDate[emp.id]?.[dayKeyIso]?.reduce((sum, s) => sum + s.hours, 0) || 0;
  if (currentDayHours + shift.hours > maxPerDay) return false;

  const weeklyTarget = emp.weeklyTarget || 60;
  if (emp.weeklyHours + shift.hours > weeklyTarget) return false;

  const preferred = preferenceMatch(emp.preferredPattern, shift.start);
  return preferred !== 'blocked';
}

function assignEmployee(emp, shift, date, assigned, assignedByDate, assignedHours) {
  assigned.push(emp.id);
  emp.weeklyHours += shift.hours;
  assignedHours[emp.id] += shift.hours;

  const dayKeyIso = date.toISOString().slice(0, 10);
  assignedByDate[emp.id] = assignedByDate[emp.id] || {};
  assignedByDate[emp.id][dayKeyIso] = assignedByDate[emp.id][dayKeyIso] || [];
  assignedByDate[emp.id][dayKeyIso].push(shift);
}

function isAvailable(emp, dayKey, start, end) {
  if (end <= start) return false;
  const { earliest, latest } = emp.availability[dayKey] || {};
  if (earliest === null || latest === null || earliest === undefined || latest === undefined || earliest === '' || latest === '') {
    return false;
  }
  return start >= earliest && end <= latest;
}

function isOverlapping(emp, date, shift, assignedByDate) {
  const dayKeyIso = date.toISOString().slice(0, 10);
  const assigned = assignedByDate[emp.id]?.[dayKeyIso] || [];
  return assigned.some(s => shift.start < s.end && shift.end > s.start);
}

function preferenceMatch(pattern, start) {
  if (!pattern) return 'neutral';
  const bucket = start < 0.25 ? 'Early' : start < 0.5 ? 'Mid' : 'Late';
  if (pattern.includes(bucket)) return 'match';
  return 'neutral';
}

function renderPlan(plan) {
  kpiEmployees.textContent = plan.employees.length;
  kpiShifts.textContent = plan.totalShiftInstances ?? plan.shifts.length;
  kpiConflicts.textContent = plan.conflicts;

  if (!plan.days.length) {
    clearPlan();
    return;
  }

  schedule.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'week-grid';

  grid.appendChild(buildTimeColumn());
  plan.days.forEach(day => {
    const col = document.createElement('div');
    col.className = 'day-col';

    const header = document.createElement('div');
    header.className = 'day-header';
    header.textContent = day.label;
    col.appendChild(header);

    const dayGrid = document.createElement('div');
    dayGrid.className = 'day-grid';

    if (!day.shifts.length) {
      const empty = document.createElement('div');
      empty.className = 'schedule-empty';
      empty.textContent = 'Keine Schichten';
      dayGrid.appendChild(empty);
    } else {
      const blocks = buildLaneLayout(day.shifts);
      blocks.forEach(block => {
        const card = document.createElement('div');
        const isUnder = block.assigned.length < block.shift.required;
        card.className = `shift-block${isUnder ? ' warn' : ''}`;

        const title = document.createElement('div');
        title.className = 'shift-time';
        title.textContent = `${formatTime(block.shift.start)}–${formatTime(block.shift.end)}`;

        const meta = document.createElement('div');
        meta.className = 'shift-people';
        meta.textContent = block.assigned.length ? block.assigned.join(', ') : 'Noch niemand';

        const role = document.createElement('div');
        role.className = 'shift-people';
        role.textContent = `${block.shift.department}/${block.shift.position}`;

        card.appendChild(title);
        card.appendChild(role);
        card.appendChild(meta);

        card.style.top = `${block.start * 100}%`;
        card.style.height = `${(block.end - block.start) * 100}%`;
        card.style.left = `${block.left}%`;
        card.style.width = `${block.width}%`;

        dayGrid.appendChild(card);
      });
    }

    col.appendChild(dayGrid);
    grid.appendChild(col);
  });

  schedule.appendChild(grid);
}

function clearPlan() {
  schedule.innerHTML = '<div class="schedule-empty">Noch kein Plan generiert.</div>';
}

function buildDemoPlan() {
  const today = new Date();
  const days = [];
  for (let i = 0; i < 7; i += 1) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    days.push({
      date: d,
      label: `${DAY_KEYS[d.getDay() === 0 ? 6 : d.getDay() - 1]} ${formatDateShort(d)}`,
      shifts: [
        {
          shift: {
            department: 'FRONT',
            position: 'Kasse',
            start: 0.25,
            end: 0.5,
            required: 2
          },
          assigned: ['Mara', 'Jonas']
        }
      ]
    });
  }
  return {
    startDate: days[0].date,
    endDate: days[days.length - 1].date,
    employees: Array(10).fill(0),
    shifts: Array(20).fill(0),
    totalShiftInstances: days.length,
    conflicts: 1,
    days
  };
}

function formatTime(value) {
  if (typeof value !== 'number') return '';
  const totalMinutes = Math.round(value * 24 * 60);
  const h = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function formatDate(date) {
  return date.toLocaleDateString('de-DE', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function formatDateShort(date) {
  return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

function parseDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function resolveStartDate(data) {
  const prefStart = getApiWeekStart(data.preferences || []);
  if (prefStart) return prefStart;
  const paramStart = parseDate(data.params.PlanningStartDate);
  if (paramStart) return paramStart;
  return getNextMonday(new Date());
}

function getApiWeekStart(preferences) {
  for (const p of preferences) {
    if (p.week_start) {
      const d = parseDate(p.week_start);
      if (d) return d;
    }
  }
  return null;
}

function getNextMonday(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  const day = d.getDay();
  const diff = ((8 - day) % 7) || 7;
  d.setDate(d.getDate() + diff);
  return d;
}

function mapDayLabel(label) {
  const map = {
    Mo: 'Mon',
    Di: 'Tue',
    Mi: 'Wed',
    Do: 'Thu',
    Fr: 'Fri',
    Sa: 'Sat',
    So: 'Sun',
    Mon: 'Mon',
    Tue: 'Tue',
    Wed: 'Wed',
    Thu: 'Thu',
    Fri: 'Fri',
    Sat: 'Sat',
    Sun: 'Sun'
  };
  return map[label] || null;
}

function slotToWindow(slot) {
  const s = String(slot || '').toLowerCase();
  if (s === 'off' || s === 'frei') return { earliest: null, latest: null };
  if (s === 'early' || s === 'früh' || s === 'frueh') return { earliest: 0.0, latest: 0.5 };
  if (s === 'late' || s === 'spät' || s === 'spaet') return { earliest: 0.5, latest: 1.0 };
  if (s === 'mid') return { earliest: 0.25, latest: 0.75 };
  return { earliest: 0.0, latest: 1.0 };
}

function buildTimeColumn() {
  const col = document.createElement('div');
  col.className = 'time-col';
  for (let h = 0; h < 24; h += 1) {
    const label = document.createElement('div');
    label.className = 'time-label';
    label.textContent = `${String(h).padStart(2, '0')}:00`;
    col.appendChild(label);
  }
  return col;
}

function buildLaneLayout(entries) {
  const blocks = entries.map(entry => ({
    shift: entry.shift,
    assigned: entry.assigned,
    start: entry.shift.start,
    end: entry.shift.end
  }));

  blocks.sort((a, b) => a.start - b.start || a.end - b.end);
  const lanes = [];
  blocks.forEach(block => {
    let laneIndex = lanes.findIndex(end => end <= block.start);
    if (laneIndex === -1) {
      lanes.push(block.end);
      laneIndex = lanes.length - 1;
    } else {
      lanes[laneIndex] = block.end;
    }
    block.lane = laneIndex;
  });

  const laneCount = Math.max(1, lanes.length);
  const gap = 2;
  const width = (100 - gap * (laneCount + 1)) / laneCount;
  blocks.forEach(block => {
    block.left = gap + block.lane * (width + gap);
    block.width = width;
  });

  return blocks;
}

function toNumber(value) {
  if (value === '' || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}
