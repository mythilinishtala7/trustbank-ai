"""Deterministic synthetic fixtures. No randomness; all times are relative to `now`.

The rules here mirror `openspec/changes/trustbank-agentic-fraud-prevention/knowledge-graph-data.md`.
The data holds facts only: nothing here labels any entity as genuine or suspicious.
"""

from datetime import datetime, timedelta
from zlib import crc32

from trustbank.domain import (
    Account,
    Beneficiary,
    Connection,
    ConnectionKind,
    Customer,
    Dataset,
    OwnerType,
    Transaction,
)

SHOPPER_NAMES = (
    "Anil K.", "Bhavna S.", "Chetan R.", "Deepa M.", "Esha P.", "Farhan Q.",
    "Gita N.", "Harsh V.", "Isha D.", "Jatin L.", "Kavya T.", "Lalit G.",
)  # fmt: skip
PAYER_NAMES = (
    "Karan S.", "Meera P.", "Imran K.", "Divya R.", "Rohit M.", "Sana A.", "Vikram T.", "Neha B.",
)  # fmt: skip

# Inbound payments into the entry account of the forwarding chain: (amount, hours ago).
CHAIN_INBOUND = (
    (8_000, 70), (12_000, 60), (5_000, 50), (9_500, 41),
    (6_000, 30), (15_000, 22), (7_000, 12), (11_000, 5),
)  # fmt: skip
CHAIN_ACCOUNTS = ("ben_novatrade", "ben_quickreturns", "ben_taskrewards", "ben_swiftassist")
CHAIN_GAPS_MINUTES = (6, 4, 5)
CHAIN_PERCENT_OF_INBOUND = (98, 97, 96)


def account_id(owner_id: str) -> str:
    return "acct_" + owner_id.split("_", 1)[1]


def _round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


class _Builder:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.customers: list[Customer] = []
        self.beneficiaries: list[Beneficiary] = []
        self.accounts: list[Account] = []
        self.transactions: list[Transaction] = []
        self.connections: list[Connection] = []

    def at_day(self, days_ago: int, hour: int, minute: int = 0) -> datetime:
        midnight = (self.now - timedelta(days=days_ago)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return midnight + timedelta(hours=hour, minutes=minute)

    def hours_ago(self, hours: int) -> datetime:
        return self.now - timedelta(hours=hours)

    def _account(self, owner_id: str, owner_type: OwnerType, opened_at: datetime) -> None:
        number = str(500_000_000_000 + crc32(owner_id.encode()) % 100_000_000)
        masked = f"XXXXXXXX{number[-4:]}"
        self.accounts.append(
            Account(
                id=account_id(owner_id),
                owner_id=owner_id,
                owner_type=owner_type,
                opened_at=opened_at,
                account_number=number,
                masked_number=masked,
            )
        )

    def customer(
        self, cid: str, name: str, balance: int, age_days: int, handle: str, persona: bool = False
    ) -> None:
        self.customers.append(
            Customer(
                id=cid, display_name=name, handle=handle, balance=balance, is_demo_persona=persona
            )
        )
        self._account(cid, OwnerType.CUSTOMER, self.now - timedelta(days=age_days))

    def beneficiary(self, bid: str, name: str, handle: str, age_days: int) -> None:
        first_seen = self.now - timedelta(days=age_days)
        self.beneficiaries.append(
            Beneficiary(id=bid, display_name=name, handle=handle, first_seen_at=first_seen)
        )
        self._account(bid, OwnerType.BENEFICIARY, first_seen)

    def txn(
        self,
        tid: str,
        source_owner: str,
        beneficiary_id: str,
        amount: int,
        note: str,
        timestamp: datetime,
    ) -> None:
        self.transactions.append(
            Transaction(
                id=tid,
                source_account_id=account_id(source_owner),
                beneficiary_id=beneficiary_id,
                amount=amount,
                note=note,
                timestamp=timestamp,
            )
        )

    def connect(self, cid: str, a: str, b: str, kind: ConnectionKind) -> None:
        self.connections.append(
            Connection(id=cid, account_a_id=account_id(a), account_b_id=account_id(b), kind=kind)
        )

    def build(self) -> Dataset:
        return Dataset(
            customers=tuple(self.customers),
            beneficiaries=tuple(self.beneficiaries),
            accounts=tuple(self.accounts),
            transactions=tuple(self.transactions),
            connections=tuple(self.connections),
        )


def _shopper(i: int) -> str:
    return f"cust_s{(i - 1) % 12 + 1:02d}"


def _people(b: _Builder) -> None:
    b.customer("cust_asha", "Asha Menon", 500_000, 400, "asha.menon@trustpay", persona=True)
    b.customer("cust_priya", "Priya Nair", 12_400, 120, "priya.nair@trustpay", persona=True)
    b.customer(
        "cust_dmart", "DMart Groceries Pvt Ltd", 2_500_458, 1_800, "dmart.groceries@trustpay",
        persona=True,
    )  # fmt: skip
    for i, name in enumerate(SHOPPER_NAMES, start=1):
        cid = f"cust_s{i:02d}"
        b.customer(cid, name, 0, 300, f"{cid[5:]}@trustpay")
    for i, name in enumerate(PAYER_NAMES, start=1):
        cid = f"cust_p{i:02d}"
        b.customer(cid, name, 0, 200, f"{cid[5:]}@trustpay")

    for bid, name, handle, age in (
        ("ben_rahul", "Rahul Verma", "rahul.verma@trustpay", 400),
        ("ben_freshmart", "Fresh Mart Grocers", "freshmart@trustpay", 300),
        ("ben_citypower", "City Power Board", "citypower@trustpay", 500),
        ("ben_metrocafe", "Metro Cafe", "metrocafe@trustpay", 200),
        ("ben_ananya", "Ananya Rao", "ananya.rao@trustpay", 20),
        ("ben_sharma_store", "Sharma General Store", "sharma.store@trustpay", 700),
        ("ben_wholesale_hub", "Wholesale Hub", "wholesale.hub@trustpay", 900),
        ("ben_greenleaf", "Green Leaf Bakery", "greenleaf.bakery@trustpay", 25),
        ("ben_heritage", "Heritage Jewellers", "heritage.jewellers@trustpay", 600),
        ("ben_spice_garden", "Spice Garden Restaurant", "spice.garden@trustpay", 500),
        ("ben_spice_owner", "Spice Garden (owner account)", "spice.owner@trustpay", 500),
        ("ben_dmart_sales", "DMart Groceries Pvt Ltd (store sales)", "dmart.sales@trustpay", 1_800),
        ("ben_dm_fmcg", "Sunrise FMCG Distributors", "sunrise.fmcg@trustpay", 1_500),
        ("ben_dm_produce", "Fresh Farm Produce Co-op", "freshfarm.coop@trustpay", 1_400),
        ("ben_dm_freight", "Metro Logistics & Freight", "metro.freight@trustpay", 1_200),
        ("ben_dm_realty", "Orchid Realty (store lease)", "orchid.realty@trustpay", 1_700),
        ("ben_dm_gst", "GST Payment Portal", "gst.portal@trustpay", 1_800),
        ("ben_dm_payroll", "Staff Payroll Services", "staff.payroll@trustpay", 1_600),
        ("ben_dm_pack", "PackWell Packaging Supplies", "packwell@trustpay", 900),
        ("ben_dm_clean", "SparkClean Housekeeping", "sparkclean@trustpay", 800),
        ("ben_dm_tea", "Raju Tea & Snacks", "raju.tea@trustpay", 700),
        ("ben_novatrade", "Nova Trade Desk", "nova.trade@trustpay", 3),
        ("ben_quickreturns", "Quick Returns Hub", "quick.returns@trustpay", 6),
        ("ben_taskrewards", "Task Rewards Desk", "task.rewards@trustpay", 11),
        ("ben_swiftassist", "Swift Assist Services", "swift.assist@trustpay", 9),
    ):
        b.beneficiary(bid, name, handle, age)


def _asha_and_priya(b: _Builder) -> None:
    history = (
        ("ben_rahul", 2_500, "September rent", 43),
        ("ben_rahul", 2_500, "August rent", 74),
        ("ben_rahul", 2_500, "July rent", 104),
        ("ben_freshmart", 1_850, "Groceries", 5),
        ("ben_freshmart", 1_240, "Groceries", 19),
        ("ben_freshmart", 2_100, "Groceries", 33),
        ("ben_citypower", 1_960, "Electricity bill", 12),
        ("ben_metrocafe", 480, "Lunch", 2),
        ("ben_metrocafe", 360, "Coffee", 9),
    )
    for i, (ben, amount, note, days) in enumerate(history, start=1):
        b.txn(f"txn_hist_{i}", "cust_asha", ben, amount, note, b.at_day(days, 12))
    b.txn("txn_priya_1", "cust_priya", "ben_ananya", 1_200, "Shared dinner", b.at_day(20, 12))
    b.txn("txn_priya_2", "cust_priya", "ben_metrocafe", 300, "Coffee", b.at_day(8, 12))


def _sharma_store(b: _Builder) -> None:
    for i in range(1, 121):
        day = 1 + _round_half_up((i - 1) * 59, 119)
        minute_of_day = 10 * 60 + (i * 37) % 600
        b.txn(
            f"txn_shop_{i:03d}",
            _shopper(i),
            "ben_sharma_store",
            80 + (i * 379) % 1721,
            "Store purchase",
            b.at_day(day, 0, minute_of_day),
        )
    for k in range(8):
        b.txn(
            f"txn_shop_out_{k + 1}",
            "ben_sharma_store",
            "ben_wholesale_hub",
            6_000,
            "Weekly supplier payment",
            b.at_day(3 + 7 * k, 10),
        )
    b.connect(
        "conn_sharma_wholesale",
        "ben_sharma_store",
        "ben_wholesale_hub",
        ConnectionKind.BUSINESS_SUPPLIER,
    )


def _small_merchants(b: _Builder) -> None:
    leaf_senders = (1, 2, 3, 4, 5, 6, 1, 2)
    leaf_days = (1, 3, 5, 8, 11, 14, 18, 23)
    for i, (sender, day) in enumerate(zip(leaf_senders, leaf_days, strict=True), start=1):
        b.txn(
            f"txn_leaf_{i}",
            f"cust_s{sender:02d}",
            "ben_greenleaf",
            150 + (i * 137) % 751,
            "Bakery order",
            b.at_day(day, 12),
        )
    for i in range(1, 21):
        b.txn(
            f"txn_jewel_{i}",
            _shopper(i),
            "ben_heritage",
            5_000 + (i * 7919) % 55_001,
            "Jewellery purchase",
            b.at_day(4 * i, 14),
        )


def _restaurant(b: _Builder) -> None:
    # TODO: Restore graph-flow coverage after reconciling intended restaurant dwell range.
    slots = ((12, 30), (15, 30), (20, 0))
    for day in range(1, 21):
        total = 0
        for slot, (hour, minute) in enumerate(slots):
            i = (day - 1) * 3 + slot + 1
            amount = 200 + (i * 313) % 1301
            total += amount
            b.txn(
                f"txn_spice_in_{i}",
                _shopper(i),
                "ben_spice_garden",
                amount,
                "Dining",
                b.at_day(day, hour, minute),
            )
        b.txn(
            f"txn_spice_out_{day}",
            "ben_spice_garden",
            "ben_spice_owner",
            _round_half_up(total * 95, 100),
            "Daily sweep",
            b.at_day(day, 23),
        )
    b.connect("conn_spice_owner", "ben_spice_garden", "ben_spice_owner", ConnectionKind.SAME_OWNER)


def _dmart(b: _Builder) -> None:
    """A business customer with big-ticket (suppliers, rent, tax, payroll) and small-ticket spend."""
    src = "cust_dmart"
    for d in range(1, 91):
        for slot in range(3):
            i = (d - 1) * 3 + slot + 1
            b.txn(
                f"txn_dm_sale_{i}", _shopper(i), "ben_dmart_sales", 200 + (i * 463) % 4301,
                "Grocery purchase", b.at_day(d, 10 + slot * 4, (i * 13) % 60),
            )  # fmt: skip
        if d % 7 == 0:
            b.txn(
                f"txn_dm_bulk_{d // 7}", _shopper(d), "ben_dmart_sales", 50_000 + (d * 12_347) % 150_001,
                "Bulk order", b.at_day(d, 12, 30),
            )  # fmt: skip
    for k in range(13):
        b.txn(
            f"txn_dm_fmcg_{k + 1}", src, "ben_dm_fmcg", 350_000 + (k * 91_300) % 550_001,
            "Weekly FMCG stock", b.at_day(2 + 7 * k, 10, 30),
        )  # fmt: skip
    for k in range(26):
        b.txn(
            f"txn_dm_produce_{k + 1}", src, "ben_dm_produce", 40_000 + (k * 17_900) % 80_001,
            "Fresh produce", b.at_day(1 + 3 * k, 6, 15),
        )  # fmt: skip
    for k in range(13):
        b.txn(
            f"txn_dm_freight_{k + 1}", src, "ben_dm_freight", 25_000 + (k * 7_700) % 35_001,
            "Freight and unloading", b.at_day(3 + 7 * k, 15),
        )  # fmt: skip
    for m in range(3):
        day = 30 * m + 1
        b.txn(f"txn_dm_rent_{m + 1}", src, "ben_dm_realty", 450_000, "Store rent", b.at_day(day, 9))
        b.txn(f"txn_dm_gst_{m + 1}", src, "ben_dm_gst", 680_000 + m * 42_500, "GST payment", b.at_day(day + 4, 11))
        b.txn(f"txn_dm_payroll_{m + 1}", src, "ben_dm_payroll", 1_100_000 + m * 35_000, "Monthly salaries", b.at_day(day + 2, 17))
        b.txn(f"txn_dm_power_{m + 1}", src, "ben_citypower", 118_000 + m * 6_400, "Electricity bill", b.at_day(day + 8, 12))  # fmt: skip
    for d in range(1, 61):
        b.txn(
            f"txn_dm_tea_{d}", src, "ben_dm_tea", 150 + (d * 83) % 451,
            "Staff tea and snacks", b.at_day(d, 16, 10),
        )  # fmt: skip
        if d % 2 == 0:
            b.txn(
                f"txn_dm_clean_{d}", src, "ben_dm_clean", 500 + (d * 61) % 2001,
                "Cleaning supplies", b.at_day(d, 8, 45),
            )  # fmt: skip
        if d % 3 == 0:
            b.txn(
                f"txn_dm_pack_{d}", src, "ben_dm_pack", 800 + (d * 97) % 2701,
                "Bags and packaging", b.at_day(d, 13, 20),
            )  # fmt: skip


def _forwarding_chain(b: _Builder) -> None:
    for k, (amount, hours) in enumerate(CHAIN_INBOUND, start=1):
        arrival = b.hours_ago(hours)
        b.txn(f"net_in_{k}", f"cust_p{k:02d}", CHAIN_ACCOUNTS[0], amount, "Payment", arrival)
        moment = arrival
        for hop in range(3):
            moment += timedelta(minutes=CHAIN_GAPS_MINUTES[hop])
            b.txn(
                f"net_h{hop + 1}_{k}",
                CHAIN_ACCOUNTS[hop],
                CHAIN_ACCOUNTS[hop + 1],
                _round_half_up(amount * CHAIN_PERCENT_OF_INBOUND[hop], 100),
                "Transfer",
                moment,
            )


def build_dataset(now: datetime) -> Dataset:
    """Build the full synthetic dataset relative to `now` (timezone-aware)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    b = _Builder(now)
    _people(b)
    _asha_and_priya(b)
    _sharma_store(b)
    _small_merchants(b)
    _restaurant(b)
    _dmart(b)
    _forwarding_chain(b)
    return b.build()
