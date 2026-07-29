"""Validated Pydantic request models for KTV Control."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TimedRequestModel(RequestModel):
    duration_type: Literal["timed", "unlimited"] = "timed"
    duration_minutes: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_timed_duration(self) -> Self:
        if self.duration_type == "timed" and self.duration_minutes is None:
            raise ValueError("限时操作必须提供大于 0 的时长")
        return self


class OpenRequest(TimedRequestModel):
    room_ip: str = Field(min_length=1, max_length=64)
    room_name: str = Field(min_length=1, max_length=64)
    customer_type: Literal["retail", "member"] = "retail"
    member_phone: str | None = Field(default=None, max_length=32)
    member_password: str | None = Field(default=None, max_length=64)


class CloseRequest(RequestModel):
    room_ip: str = Field(min_length=1, max_length=64)
    room_name: str = Field(min_length=1, max_length=64)


class ExtendRequest(RequestModel):
    room_ip: str = Field(min_length=1, max_length=64)
    room_name: str = Field(min_length=1, max_length=64)
    duration_minutes: int = Field(gt=0)


class BookingRequest(TimedRequestModel):
    room_ip: str = Field(min_length=1, max_length=64)
    room_name: str = Field(min_length=1, max_length=64)
    open_at: str = Field(min_length=1, max_length=64)
    package_id: int | None = Field(default=None, gt=0)
    customer_type: Literal["retail", "member"] = "retail"
    member_phone: str | None = Field(default=None, max_length=32)
    member_password: str | None = Field(default=None, max_length=64)


class CreateMemberRequest(RequestModel):
    name: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=3, max_length=32)



class UpdateMemberRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=3, max_length=32)
    balance: float | None = Field(default=None, ge=0)



class ResetMemberPasswordRequest(RequestModel):
    admin_password: str
    new_password: str = Field(min_length=4, max_length=64)


class RechargeRequest(RequestModel):
    amount: float = Field(gt=0)
    payment_method: Literal["现金", "微信", "支付宝"] = "现金"


class CreatePackageRequest(RequestModel):
    name: str = Field(min_length=1, max_length=64)
    type: Literal["open", "extend"] = "open"
    duration_minutes: int = Field(gt=0)
    price_normal: float = Field(default=0, ge=0)





class UpdatePackageRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: Literal["open", "extend"] | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price_normal: float | None = Field(default=None, ge=0)



    admin_password: str


class DeletePackageRequest(RequestModel):
    admin_password: str


class CreateInventoryRequest(RequestModel):
    category: Literal["酒水", "零食", "水果"] = "酒水"
    name: str = Field(min_length=1, max_length=64)
    unit_price: float = Field(default=0, ge=0)
    cost_price: float = Field(default=0, ge=0)
    stock: int = Field(default=0, ge=0)


class UpdateInventoryRequest(RequestModel):
    category: Literal["酒水", "零食", "水果"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=64)
    unit_price: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    admin_password: str | None = None


class CreateStaffRequest(RequestModel):
    name: str = Field(min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    position: str = Field(default="员工", min_length=1, max_length=32)
    status: Literal["在职", "离职"] = "在职"
    salary: float = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=200)


class UpdateStaffRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    position: str | None = Field(default=None, min_length=1, max_length=32)
    status: Literal["在职", "离职"] | None = None
    salary: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=200)

class AddDrinkRequest(RequestModel):
    billing_id: int = Field(gt=0)
    item_name: str = Field(min_length=1, max_length=64)
    qty: int = Field(default=1, gt=0)
    unit_price: float | None = Field(default=None, ge=0)


class UpdateBillingRequest(RequestModel):
    duration_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=200)


class SaveBillingDraftRequest(RequestModel):
    package_id: int = Field(gt=0)
    payment_method: Literal["\u73b0\u91d1", "\u5fae\u4fe1", "\u652f\u4ed8\u5b9d", "\u4f1a\u5458\u4f59\u989d"] = "\u73b0\u91d1"
    discount: float = Field(default=0, ge=0)

class SettlementRequest(RequestModel):
    billing_id: int = Field(gt=0)
    package_id: int = Field(gt=0)
    payment_method: Literal["现金", "微信", "支付宝", "会员余额"] = "现金"
    discount: float = Field(default=0, ge=0)
    member_phone: str | None = Field(default=None, max_length=32)
    member_password: str | None = Field(default=None, max_length=64)


class VerifyMemberRequest(RequestModel):
    phone: str = Field(min_length=3, max_length=32)
    password: str = Field(max_length=64)


class VerifyAdminRequest(RequestModel):
    admin_password: str