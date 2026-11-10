import { notifications } from "@mantine/notifications";
import i18n from "./i18n";

/** Short success toast for CRUD / copy actions. */
export function notifySuccess(message: string, title?: string): void {
  notifications.show({
    color: "green",
    title: title ?? i18n.t("common.notice"),
    message,
    autoClose: 3500,
  });
}

/** Error toast; keep page Alerts for form-local validation. */
export function notifyError(message: string, title?: string): void {
  notifications.show({
    color: "red",
    title: title ?? i18n.t("common.error"),
    message,
    autoClose: 6000,
  });
}
