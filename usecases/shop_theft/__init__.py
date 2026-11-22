from ..base import UseCase


class ShopTheft(UseCase):
    name = "Shop Theft Alert"
    description = "Watches store aisles for people hiding items in bags, pockets or clothing."
    prompt = ("You are a store security camera. Look for anyone concealing merchandise: putting items "
              "into a bag, pocket, jacket or clothing instead of a cart or basket. "
              "If you see it, reply exactly 'ALERT: <short description>'. Otherwise reply exactly 'CLEAR'.")
    hits_needed = 2


USECASE = ShopTheft()
