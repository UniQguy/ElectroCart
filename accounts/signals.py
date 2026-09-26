from django.db.models.signals import post_save
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile, Cart, CartItem


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()


@receiver(user_logged_in)
def merge_guest_cart_on_login(sender, request, user, **kwargs):
    if not request or not hasattr(request, 'session'):
        return

    cart_id = request.session.get('cart_id')
    guest_cart = None

    if cart_id:
        guest_cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()

    if not guest_cart and request.session.session_key:
        guest_cart = Cart.objects.filter(session_key=request.session.session_key, user__isnull=True).first()

    if not guest_cart:
        return

    user_cart, _ = Cart.objects.get_or_create(user=user)

    for guest_item in list(guest_cart.items.select_related('product').all()):
        user_item = user_cart.items.filter(product=guest_item.product).first()
        if user_item:
            user_item.quantity += guest_item.quantity
            user_item.save(update_fields=['quantity'])
            guest_item.delete()
        else:
            guest_item.cart = user_cart
            guest_item.save(update_fields=['cart'])

    guest_cart.delete()

    if 'cart_id' in request.session:
        del request.session['cart_id']
        request.session.modified = True