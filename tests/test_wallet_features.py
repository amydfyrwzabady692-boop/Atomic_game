import pytest
from core.models import TelegramUser
from wallet.models import EconomySettings, SellRequest, TopUpRequest, TxType
from wallet.services import InsufficientFunds, apply_transaction, transfer_coins


@pytest.mark.django_db
def test_economy_settings_defaults():
    eco = EconomySettings.load()
    assert eco.coin_price_toman == 10000
    assert eco.topup_fee_percent == 10
    assert eco.min_sell_coins == 10
    assert eco.coin_sell_price_toman == 10000


@pytest.mark.django_db
def test_transfer_coins_success():
    sender = TelegramUser.objects.create(tg_id=101, username="sender", first_name="Sender", coins=50)
    receiver = TelegramUser.objects.create(tg_id=102, username="receiver", first_name="Receiver", coins=10)

    tx_out, tx_in = transfer_coins(sender, receiver, 20)

    sender.refresh_from_db()
    receiver.refresh_from_db()

    assert sender.coins == 30
    assert receiver.coins == 30
    assert tx_out.amount == -20
    assert tx_out.type == TxType.TRANSFER_OUT
    assert tx_in.amount == 20
    assert tx_in.type == TxType.TRANSFER_IN


@pytest.mark.django_db
def test_transfer_coins_insufficient_funds():
    sender = TelegramUser.objects.create(tg_id=103, username="sender2", first_name="Sender2", coins=5)
    receiver = TelegramUser.objects.create(tg_id=104, username="receiver2", first_name="Receiver2", coins=10)

    with pytest.raises(InsufficientFunds):
        transfer_coins(sender, receiver, 10)

    sender.refresh_from_db()
    assert sender.coins == 5


@pytest.mark.django_db
def test_transfer_coins_self_transfer():
    sender = TelegramUser.objects.create(tg_id=105, username="self_user", first_name="Self", coins=50)
    with pytest.raises(ValueError):
        transfer_coins(sender, sender, 10)


@pytest.mark.django_db
def test_topup_flow():
    user = TelegramUser.objects.create(tg_id=106, username="topup_user", first_name="Buyer", coins=0)
    eco = EconomySettings.load()

    coins = 10
    amount = coins * eco.coin_price_toman
    fee = (amount * eco.topup_fee_percent) // 100
    total = amount + fee

    assert amount == 100000
    assert fee == 10000
    assert total == 110000

    req = TopUpRequest.objects.create(
        user=user,
        coins=coins,
        amount_toman=amount,
        fee_toman=fee,
        total_toman=total,
        receipt_photo_id="photo_xyz_123",
    )
    assert req.status == TopUpRequest.Status.PENDING

    # Approve
    apply_transaction(user, req.coins, TxType.TOPUP, f"topup:{req.pk}")
    req.status = TopUpRequest.Status.APPROVED
    req.save()

    user.refresh_from_db()
    assert user.coins == 10


@pytest.mark.django_db
def test_sell_flow_and_refund():
    user = TelegramUser.objects.create(tg_id=107, username="seller", first_name="Seller", coins=25)
    eco = EconomySettings.load()

    coins = 10
    amount = coins * eco.coin_sell_price_toman

    # Deduct coins on submission
    apply_transaction(user, -coins, TxType.SELL, "test_sell_1")
    user.refresh_from_db()
    assert user.coins == 15

    req = SellRequest.objects.create(
        user=user,
        coins=coins,
        amount_toman=amount,
        card_number="6037991234567890",
        card_holder="User",
    )
    assert req.status == SellRequest.Status.PENDING

    # If rejected, refund coins
    apply_transaction(user, req.coins, TxType.REFUND, f"sell_refund:{req.pk}")
    req.status = SellRequest.Status.REJECTED
    req.save()

    user.refresh_from_db()
    assert user.coins == 25
