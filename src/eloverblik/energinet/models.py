from datetime import datetime
from typing import List, Optional, Self

from attr import dataclass
from pydantic import AliasGenerator, BaseModel, ConfigDict, Field, RootModel
from pydantic.alias_generators import to_camel


@dataclass
class MeteringPoint(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        )
    )

    street_code: str
    street_name: str
    floor_id: str
    room_id: str
    city_sub_division_name: str | None
    municipality_code: str
    location_description: str | None
    settlement_method: str
    meter_reading_occurrence: str  # ISO 8601 duration
    first_consumer_party_name: str
    second_consumer_party_name: str | None
    meter_number: str
    consumer_start_date: datetime
    metering_point_id: str
    type_of_mp: str = Field(validation_alias="typeOfMP", serialization_alias="typeOfMP")
    balance_supplier_name: str
    postcode: str
    city_name: str
    has_relation: bool
    consumer_cvr: str | None = Field(
        validation_alias="consumerCVR", serialization_alias="consumerCVR"
    )
    data_access_cvr: str | None = Field(
        validation_alias="dataAccessCVR", serialization_alias="dataAccessCVR"
    )
    child_metering_points: list[Self]


class SenderMarketParticipantMRID(BaseModel):
    coding_scheme: Optional[str] = Field(
        None, validation_alias="codingScheme", description="Fixed value = A10"
    )
    name: Optional[str] = Field(
        None,
        description="GLN (Global Location Number) of DataHub. Fixed value = 5790001330583",
    )


class TimeInterval(BaseModel):
    start: Optional[datetime] = Field(
        None, description="Start date of period in UTC (ISO 8601)."
    )
    end: Optional[datetime] = Field(
        None, description="End date of period in UTC (ISO 8601)."
    )


class MarketEvaluationPointMRID(BaseModel):
    coding_scheme: Optional[str] = Field(None, validation_alias="codingScheme")
    name: Optional[str] = Field(
        None, description="Unique metering point id consisting of 18 characters."
    )


class MarketEvaluationPoint(BaseModel):
    m_rid: Optional[MarketEvaluationPointMRID] = Field(None, validation_alias="mRID")


class DataPoint(BaseModel):
    position: Optional[str] = Field(None, description="Possible values: 1-96")
    quantity: Optional[str] = Field(
        None, validation_alias="out_Quantity.quantity", description="Max 3 decimals"
    )
    quality: Optional[str] = Field(None, validation_alias="out_Quantity.quality")


class EnergyPeriod(BaseModel):
    resolution: Optional[str] = Field(
        None, description="Ex: PT15M, PT1H, P1D, P1M, P1Y"
    )
    time_interval: Optional[TimeInterval] = Field(None, validation_alias="timeInterval")
    points: Optional[List[DataPoint]] = Field(None, validation_alias="Point")


class TimeSeriesItem(BaseModel):
    m_rid: Optional[str] = Field(
        None,
        validation_alias="mRID",
        description="Unique metering point id (18 chars).",
    )
    business_type: Optional[str] = Field(
        None, validation_alias="businessType", description="A01, A04, A64"
    )
    curve_type: Optional[str] = Field(
        None, validation_alias="curveType", description="Always A01"
    )
    measurement_unit_name: Optional[str] = Field(
        None, validation_alias="measurement_Unit.name"
    )
    market_evaluation_point: Optional[MarketEvaluationPoint] = Field(
        None, validation_alias="MarketEvaluationPoint"
    )
    periods: Optional[List[EnergyPeriod]] = Field(None, validation_alias="Period")


class MyEnergyDataMarketDocument(BaseModel):
    m_rid: Optional[str] = Field(
        None,
        validation_alias="mRID",
        description="Identification of the market document.",
    )
    created_date_time: Optional[datetime] = Field(
        None, validation_alias="createdDateTime"
    )
    sender_name: Optional[str] = Field(
        None, validation_alias="sender_MarketParticipant.name"
    )
    sender_m_rid: Optional[SenderMarketParticipantMRID] = Field(
        None, validation_alias="sender_MarketParticipant.mRID"
    )
    period_time_interval: Optional[TimeInterval] = Field(
        None, validation_alias="period.timeInterval"
    )
    time_series: Optional[List[TimeSeriesItem]] = Field(
        None, validation_alias="TimeSeries"
    )


class ResponseItem(BaseModel):
    success: bool = Field(
        ..., description="True if the request succeeded, False if not"
    )
    error_code: Optional[int] = Field(None, validation_alias="errorCode")
    error_text: Optional[str] = Field(None, validation_alias="errorText")
    id: Optional[str] = Field(
        None, description="Used to map requests to responses (e.g. metering point id)"
    )
    stack_trace: Optional[str] = Field(None, validation_alias="stackTrace")
    market_document: Optional[MyEnergyDataMarketDocument] = Field(
        None, validation_alias="MyEnergyData_MarketDocument"
    )


# Because the root of your JSON is an Array/List, we wrap it in a RootModel
class EnergyDataResponse(RootModel[List[ResponseItem]]):
    pass
