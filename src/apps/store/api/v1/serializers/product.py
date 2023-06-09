import pytz
from babel.dates import format_datetime
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from apps.store.models.product import Buy, BuyProduct, PriceProduct, Product
from apps.store.models.users import UserClient
from config.settings.base import EMAIL_HOST_USER


class BuyTotalsSerializer(serializers.Serializer):
    total_amount = serializers.FloatField()
    total_remaining_amount = serializers.FloatField()
    total_recovered = serializers.FloatField()


class RevenueTotalsSerializer(serializers.Serializer):
    total_expected_revenue = serializers.FloatField()
    total_potential_revenue = serializers.FloatField()
    total_revenue = serializers.FloatField()


class BuySerializer(serializers.ModelSerializer):
    class Meta:
        model = Buy
        fields = ["date_purchase", "remaining_amount", "amount", "user_client"]


class ProductInfoSerializer(serializers.ModelSerializer):
    sale_price = serializers.FloatField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "code", "name", "stock", "sale_price", "image"]


class BuyClientProductSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = BuyProduct
        fields = ("product", "quantity")

    def validate(self, data):
        product = data["product"]
        quantity = data["quantity"]
        if quantity > product.stock:
            raise serializers.ValidationError(
                {
                    "product": f"You want {quantity} {product.name}, but there is only {product.stock} {product.name}, that is, there is not enough stock for the product {product.name}"
                }
            )

        return data


class BuyClientSerializer(serializers.Serializer):
    client_code = serializers.IntegerField()
    payment = serializers.FloatField()
    products = BuyClientProductSerializer(many=True)

    def validate(self, data):
        client_code = data["client_code"]
        user_client = UserClient.objects.filter(code=client_code)
        if not user_client.exists():
            raise serializers.ValidationError(
                {"client_code": f"There is no user with code {client_code}"}
            )
        return data

    @transaction.atomic
    def create(self, validated_data):
        payment_client = validated_data["payment"]
        client_code = validated_data["client_code"]
        user_client = UserClient.objects.get(code=client_code)

        buy_instance, _ = Buy.objects.get_or_create(
            user_client=user_client,
            date_purchase=timezone.now(),
            amount=0,
            remaining_amount=0,
        )
        buy_total_amount = 0
        remaining_amount_buy_total = 0

        # Crea instancias de BuyProduct y actualiza los stocks de los productos
        buy_products = []
        products_to_update_stock = []
        buy_message = ""
        for product_data in validated_data["products"]:
            product = product_data["product"]
            quantity = product_data["quantity"]
            price_product = PriceProduct.objects.filter(product=product).latest(
                "date_purchase"
            )

            sale_price_product = price_product.sale_price
            amount_product = sale_price_product * quantity
            remaining_amount_product = amount_product

            buy_message += "\n"
            buy_message += f"Producto: {product.name}\n"
            buy_message += f"Cantidad: {quantity}\n"
            buy_message += f"Precio: {sale_price_product}\n"
            buy_message += f"Subtotal: {amount_product}\n"

            if payment_client > 0:
                remaining_amount_product -= payment_client
                if remaining_amount_product <= 0:
                    payment_client = abs(remaining_amount_product)
                    remaining_amount_product = 0
                else:
                    payment_client = 0
                    remaining_amount_buy_total = abs(remaining_amount_product)
            else:
                remaining_amount_buy_total += amount_product
            buy_total_amount += amount_product

            buy_products.append(
                BuyProduct(
                    buy=buy_instance,
                    product=product,
                    price_product=price_product,
                    quantity=quantity,
                    remaining_amount=remaining_amount_product,
                    amount=amount_product,
                )
            )

            product.stock = product.stock - quantity
            products_to_update_stock.append(product)

        buy_instance.remaining_amount = remaining_amount_buy_total
        buy_instance.amount = buy_total_amount
        buy_instance.save()
        BuyProduct.objects.bulk_create(buy_products)
        Product.objects.bulk_update(products_to_update_stock, ["stock"])

        # Send email buy
        if user_client.email:
            total_remaining_amount = (
                Buy.available_objects.filter(user_client=user_client).aggregate(
                    Sum("remaining_amount")
                )["remaining_amount__sum"]
                or 0
            )
            user_name = user_client.name
            user_email = user_client.email
            time_zone_convetion = pytz.timezone(settings.TIME_ZONE)
            date_purchase = buy_instance.date_purchase.astimezone(time_zone_convetion)
            formatted_date = format_datetime(
                date_purchase, format="EEEE dd MMMM yyyy hh:mm:ss a", locale="es"
            )

            subject = f"¡Gracias por tu compra en UNICAPP, {user_name}!"

            message = f"""Hola, {user_name},

¡Gracias por comprar en nuestra tienda UNICAPP! Nos complace informarte que tu compra, realizada el {formatted_date}, ha sido procesada exitosamente. Aquí te compartimos los detalles de tu pedido:
{buy_message}

MONTO TOTAL DE TU COMPRA: {buy_instance.amount}
            """

            if buy_instance.remaining_amount > 0:
                message += f"""
Con esta compra se agregó un saldo pendiente de ${buy_instance.remaining_amount}. El total de tu saldo pendiente es de ${total_remaining_amount}. Si quieres conocer el detalle de tu historial de compras, por favor consulta la web de UNICAPP.
            """

            message += """
Si tienes alguna pregunta o inquietud sobre tu pedido, no dudes en ponerte en contacto con el equipo UNICAPP. Estaremos encantados de ayudarte.

¡Esperamos que disfrutes de tus productos y te agradecemos nuevamente por elegir UNICAPP!
            """

            sender_email = EMAIL_HOST_USER
            destination_emails = [
                user_email,
            ]
            send_mail(subject, message, sender_email, destination_emails)

        return buy_instance

    def to_representation(self, instance):
        time_zone_convetion = pytz.timezone(settings.TIME_ZONE)
        data = {
            "user_client": str(instance.user_client),
            "user_code": str(instance.user_client.code),
            "date_purchase": instance.date_purchase.astimezone(
                time_zone_convetion
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "remaining_amount": instance.remaining_amount,
            "amount": instance.amount,
        }
        return data
