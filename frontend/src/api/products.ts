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

export type ProductMatch = {
  id: number;
  title?: string | null;
  url?: string | null;
  price?: string | null;
  price_amount?: number | null;
  currency?: string | null;
  availability?: string | null;
  site_id: number;
  site_name?: string | null;
};

export type ProductMatchGroup = {
  id: number;
  identifier_type: "gtin" | "sku" | string;
  identifier_value: string;
  products: ProductMatch[];
};

export type ProductDetailContext = {
  product: Product | null;
  products: Product[];
  events: ChangeEvent[];
  variants: ProductVariant[];
  matches: ProductMatchGroup[];
  sites: Site[];
  live: boolean;
  mode: "live" | "demo";
  message: string;
};

export function loadProducts(siteId?: number): Promise<Product[]> {
  const query = siteId ? `?site_id=${siteId}` : "";
  return getJson<Product[]>(`/api/products${query}`);
}

export function loadPriceMatrix(): Promise<ProductMatchGroup[]> {
  return getJson<ProductMatchGroup[]>("/api/product-match-groups");
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
  const [variants, matches] = product && overview.live
    ? await Promise.all([
        getJson<ProductVariant[]>(`/api/products/${product.id}/variants`),
        getJson<ProductMatchGroup[]>(`/api/products/${product.id}/matches`),
      ])
    : [[], []] as [ProductVariant[], ProductMatchGroup[]];

  return {
    product,
    products: overview.products,
    events,
    variants,
    matches,
    sites: overview.sites,
    live: overview.live,
    mode: overview.mode,
    message: overview.message,
  };
}
