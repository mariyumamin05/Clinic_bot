-- appointment_db_schema.sql
-- Postgres schema for AI Voice Appointment & Scheduling Agent

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE specialties (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE doctors (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(150) NOT NULL,
    specialty_id    INTEGER NOT NULL REFERENCES specialties(id),
    bio             TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_doctors_specialty ON doctors(specialty_id);

CREATE TABLE patients (
    id                    SERIAL PRIMARY KEY,
    full_name             VARCHAR(150) NOT NULL,
    phone                 VARCHAR(20) NOT NULL UNIQUE,
    email                 VARCHAR(150),
    preferred_doctor_id   INTEGER REFERENCES doctors(id),
    preferred_time_of_day VARCHAR(20),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE doctor_availability (
    id                  SERIAL PRIMARY KEY,
    doctor_id           INTEGER NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    day_of_week         SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time          TIME NOT NULL,
    end_time            TIME NOT NULL,
    slot_duration_min   SMALLINT NOT NULL DEFAULT 30,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (end_time > start_time)
);

CREATE INDEX idx_availability_doctor_day ON doctor_availability(doctor_id, day_of_week);

-- NEW: clinic-wide closures (holidays, etc.) — Fix #4
CREATE TABLE clinic_closures (
    id              SERIAL PRIMARY KEY,
    closure_date    DATE NOT NULL UNIQUE,
    reason          VARCHAR(255)
);

CREATE TYPE appointment_status AS ENUM (
    'booked',
    'cancelled',
    'completed',
    'no_show'
);

CREATE TABLE appointments (
    id                    SERIAL PRIMARY KEY,
    doctor_id             INTEGER NOT NULL REFERENCES doctors(id),
    patient_id            INTEGER NOT NULL REFERENCES patients(id),
    appointment_time      TIMESTAMPTZ NOT NULL,
    duration_minutes      SMALLINT NOT NULL DEFAULT 30 CHECK (duration_minutes > 0),
    end_time              TIMESTAMPTZ NOT NULL,
    status                appointment_status NOT NULL DEFAULT 'booked',
    notes                 TEXT,
    cancellation_reason   TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    EXCLUDE USING gist (
        doctor_id WITH =,
        tstzrange(appointment_time, end_time) WITH &&
    ) WHERE (status = 'booked')
);

CREATE INDEX idx_appointments_doctor_time ON appointments(doctor_id, appointment_time);
CREATE INDEX idx_appointments_patient ON appointments(patient_id);
CREATE INDEX idx_appointments_status ON appointments(status);

CREATE OR REPLACE FUNCTION set_appointment_end_time()
RETURNS TRIGGER AS $$
BEGIN
    NEW.end_time = NEW.appointment_time + (NEW.duration_minutes || ' minutes')::interval;
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_appointments_set_end_time
    BEFORE INSERT OR UPDATE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION set_appointment_end_time();