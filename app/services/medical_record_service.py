from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.medical_record import MedicalRecord
from app.models.user import User


def get_patient_record(
    db: Session,
    patient_id: int,
):
    return db.scalar(
        select(MedicalRecord)
        .where(
            MedicalRecord.patient_id == patient_id
        )
    )



def create_or_update_record(
    db: Session,
    patient: User,
    blood_group: str | None,
    allergies: str | None,
    medical_conditions: str | None,
    current_medications: str | None,
):

    record = get_patient_record(
        db=db,
        patient_id=patient.id,
    )


    if record is None:

        record = MedicalRecord(
            patient_id=patient.id,
            blood_group=blood_group,
            allergies=allergies,
            medical_conditions=medical_conditions,
            current_medications=current_medications,
        )

        db.add(record)

    else:
        if blood_group is not None:
            record.blood_group = blood_group
        if allergies is not None:
            record.allergies = allergies
        if medical_conditions is not None:
            record.medical_conditions = medical_conditions
        if current_medications is not None:
            record.current_medications = current_medications


    db.commit()
    db.refresh(record)

    return record