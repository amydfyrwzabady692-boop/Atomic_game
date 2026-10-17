import pytest
from core.models import TelegramUser
from wallet.models import CoinTransaction, EconomySettings, SellRequest, TopUpRequest, TxType
from wallet.services import InsufficientFunds, apply_transaction, transfer_coins

pytestmark = pytest.mark.django_db


def test_economy_settings_defaults():
    eco = EconomySettings.load()
    assert eco.coin_price_toman == 1000
    assert eco.topup_fee_percent == 10
    assert eco.min_sell_coins == 100
    assert eco.coin_sell_price_toman == 1000


def test_transfer_coins_success(make_user):
    sender = make_user(coins=250)
    receiver = make_user(coins=50)

    out_tx, in_tx = transfer_coins(sender, receiver, 100)
    sender.refresh_from_db()
    receiver.refresh_from_db()

    assert sender.coins == 150
    assert receiver.coins == 150
    assert out_tx.type == TxType.TRANSFER_OUT
    assert out_tx.amount == -100
    assert in_tx.type == TxType.TRANSFER_IN
    assert in_tx.amount == 100


def test_transfer_coins_insufficient_funds(make_user):
    sender = make_user(coins=30)
    receiver = make_user(coins=10)

    with pytest.raises(InsufficientFunds):
        transfer_coins(sender, receiver, 50)

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.coins == 30
    assert receiver.coins == 10


def test_transfer_coins_invalid_amount_or_self(make_user):
    user = make_user(coins=100)
    other = make_user(coins=10)

    with pytest.raises(ValueError):
        transfer_coins(user, user, 50)

    with pytest.raises(ValueError):
        transfer_coins(user, other, 0)

    with pytest.raises(ValueError):
        transfer_coins(user, other, -10)


def test_topup_and_sell_models(make_user):
    user = make_user(coins=200)

    topup = TopUpRequest.objects.create(
        user=user,
        coins=100,
        amount_toman=100000,
        fee_toman=10000,
        total_toman=110000,
        receipt_photo_id="photo_123",
    )
    assert topup.status == TopUpRequest.Status.PENDING
    assert topup.total_toman == 110000

    sell = SellRequest.objects.create(
        user=user,
        coins=100,
        amount_toman=100000,
        card_number="6037991234567890",
        card_holder="User Test",
    )
    assert sell.status == SellRequest.Status.PENDING
    assert sell.coins == 100
