import { getJson } from "./client";
import { loadOverview } from "./overview";
import type { ChangeEvent, Product, Site } from "../types/api";

export type ProductVariant = {
  id: number;
  external_id: string;
  sku?: string | null;
  title?: string | null;
  option_values?: string | null;
  price?: string | null;
  price_amount?: number | null;
  compare_at_price?: number | null;
  availability?: string | null;
  is_active: boolean;
};

export type ProductDetailContext = {
  product: Product | null;
  products: Product[];
  events: ChangeEvent[];
  variants: ProductVariant[];
  sites: Site[];
  live: boolean;
  mode: "live" | "demo";
  message: string;
};

export function loadProducts(siteId?: number): Promise<Product[]> {
  const query = siteId ? `?site_id=${siteId}` : "";
  return getJson<Product[]>(`/api/products${query}`);
}

export async function loadProductDetailContext(productId: number | string): Promise<ProductDetailContext> {
  const overview = await loadOverview();
  const product = overview.products.find((item) => String(item.id) === String(productId)) || null;
  const events = overview.events.filter((event) => {
    if (!product) return false;
    return event.product_id === product.id
      || (!!event.product_url && event.product_url === product.url)
      || (!!event.product_title && event.product_title === product.title);
  });
  const variants = product && overview.live
    ? await getJson<ProductVariant[]>(`/api/products/${product.id}/variants`)
    : [];

  return {
    product,
    products: overview.products,
    events,
    variants,
    sites: overview.sites,
    live: overview.live,
    mode: overview.mode,
    message: overview.message,
  };
}
