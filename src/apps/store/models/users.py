from common.abstract_models import BaseModelClass
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver


def product_directory_path(instance, filename):

    # File will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    return "product_{0}/{1}".format(instance.id, filename)


class UserClient(BaseModelClass):
    name = models.CharField(verbose_name="Name: ", max_length=50)
    code = models.IntegerField(verbose_name="Code: ")
    email = models.EmailField(
        verbose_name="Email: ", max_length=254, null=True, blank=True
    )
    image = models.ImageField(upload_to=product_directory_path, null=True, blank=True)
    maximum_credit_value = models.FloatField(
        verbose_name="Maximun credit: ", default=400
    )
    remaining_credit = models.FloatField(verbose_name="Remaining credit: ", default=400)

    def __str__(self):
        return self.name


@receiver(pre_save, sender=UserClient)
def signal_pre_save_contract(sender, instance, **kwargs):
    query_for_ger_user_client = UserClient.available_objects.filter(pk=instance.pk)
    if not query_for_ger_user_client.exists():
        try:
            user_client_with_code_bigger = UserClient.all_objects.latest("code")
        except UserClient.DoesNotExist:
            user_client_with_code_bigger = None
        if user_client_with_code_bigger is None:
            instance.code = 10000
        else:
            last_code = user_client_with_code_bigger.code
            instance.code = last_code + 8
