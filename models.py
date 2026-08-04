"""Validated Pydantic request models for KTV Control."""

from datetime import datetime
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
    remark: str | None = Field(default=None, max_length=255)



class UpdateMemberRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=3, max_length=32)
    balance: float | None = Field(default=None, ge=0)
    remark: str | None = Field(default=None, max_length=255)



class ResetMemberPasswordRequest(RequestModel):
    new_password: str = Field(min_length=4, max_length=64)


class RechargeRequest(RequestModel):
    amount: float = Field(gt=0)
    payment_method: Literal["现金", "微信", "支付宝"] = "现金"
    notes: str | None = Field(default=None, max_length=200)


class RechargeLogWriteRequest(RequestModel):
    member_id: int = Field(gt=0)
    member_name: str = Field(min_length=1, max_length=64)
    member_phone: str = Field(min_length=3, max_length=32)
    amount: float = Field(gt=0)
    balance_after: float = Field(ge=0)
    payment_method: str = Field(min_length=1, max_length=32)
    detail: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=200)
    created_at: datetime
    admin_password: str


class StoreMemberDrinkRequest(RequestModel):
    item_name: str = Field(min_length=1, max_length=64)
    storage_kind: Literal["sealed", "opened"] = "sealed"
    quantity: int = Field(default=1, gt=0)
    remaining_level: Literal["1/4", "1/2", "3/4", "接近整瓶"] | None = None
    storage_location: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_opened_drink(self) -> Self:
        if self.storage_kind == "opened":
            if self.quantity != 1:
                raise ValueError("已开封酒每条记录数量只能为 1")
            if self.remaining_level is None:
                raise ValueError("已开封酒必须选择剩余量")
        return self


class RetrieveMemberDrinkRequest(RequestModel):
    quantity: int = Field(default=1, gt=0)
    notes: str | None = Field(default=None, max_length=200)

class PackageItemRequest(RequestModel):
    item_type: Literal["drink", "snack"]
    inventory_id: int | None = Field(default=None, gt=0)
    item_name: str | None = Field(default=None, max_length=64)
    qty: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def validate_package_item(self) -> Self:
        if self.item_type == "drink" and self.inventory_id is None:
            raise ValueError("套餐酒水必须选择库存商品")
        if self.item_type == "snack" and not (self.item_name or "").strip():
            raise ValueError("套餐小吃必须填写名称")
        return self


class CreatePackageRequest(RequestModel):
    name: str = Field(min_length=1, max_length=64)
    type: Literal["open", "extend"] = "open"
    duration_minutes: int = Field(gt=0)
    price_normal: float = Field(default=0, ge=0)
    items: list[PackageItemRequest] = Field(default_factory=list, max_length=50)


class UpdatePackageRequest(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: Literal["open", "extend"] | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price_normal: float | None = Field(default=None, ge=0)
    items: list[PackageItemRequest] | None = Field(default=None, max_length=50)


class DeletePackageRequest(RequestModel):
    admin_password: str

class CreateInventoryRequest(RequestModel):
    category: Literal["酒水", "饮料", "零食", "水果"] = "酒水"
    name: str = Field(min_length=1, max_length=64)
    unit_name: str = Field(default="瓶", min_length=1, max_length=8)
    unit_price: float = Field(default=0, ge=0)
    case_size: int = Field(default=0, ge=0)
    case_price: float = Field(default=0, ge=0)
    cost_price: float = Field(default=0, ge=0)
    stock: int = Field(default=0, ge=0)
    low_stock: int = Field(default=5, ge=0)


class UpdateInventoryRequest(RequestModel):
    category: Literal["酒水", "饮料", "零食", "水果"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=64)
    unit_name: str | None = Field(default=None, min_length=1, max_length=8)
    unit_price: float | None = Field(default=None, ge=0)
    case_size: int | None = Field(default=None, ge=0)
    case_price: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    low_stock: int | None = Field(default=None, ge=0)
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
    inventory_id: int = Field(gt=0)
    sale_unit: Literal["unit", "case"] = "unit"
    qty: int = Field(default=1, gt=0)

class UpdateBillingRequest(RequestModel):
    duration_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=200)


class SaveBillingDraftRequest(RequestModel):
    package_id: int = Field(gt=0)
    payment_method: Literal["\u73b0\u91d1", "\u5fae\u4fe1", "\u652f\u4ed8\u5b9d", "\u4f1a\u5458\u4f59\u989d"] = "\u73b0\u91d1"
    actual_total: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=200)

class SettlementRequest(RequestModel):
    billing_id: int = Field(gt=0)
    package_id: int = Field(gt=0)
    payment_method: Literal["现金", "微信", "支付宝", "会员余额"] = "现金"
    actual_total: float | None = Field(default=None, ge=0)
    member_phone: str | None = Field(default=None, max_length=32)
    member_password: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=200)


class BillingHistoryWriteRequest(RequestModel):
    room_no: str = Field(min_length=1, max_length=64)
    room_fee: float = Field(ge=0)
    drinks_fee: float = Field(ge=0)
    total: float = Field(ge=0)
    payment_method: str = Field(min_length=1, max_length=32)
    settlement_member_name: str | None = Field(default=None, max_length=64)
    settlement_member_phone: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=200)
    close_at: datetime
    admin_password: str


class VerifyMemberRequest(RequestModel):
    phone: str = Field(min_length=3, max_length=32)
    password: str = Field(max_length=64)


class VerifyAdminRequest(RequestModel):
    admin_password: str