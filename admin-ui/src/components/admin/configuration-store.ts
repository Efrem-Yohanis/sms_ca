import { useSyncExternalStore } from "react";

export type ConfigPage = "SMSC Accounts" | "Sender IDs" | "Channels";

export type ConfigEntry = {
  id: string;
  values: string[];
  active: boolean;
  subscriberEmails: string[];
};

type ConfigurationEntries = Record<ConfigPage, ConfigEntry[]>;

let configurationEntries: Partial<ConfigurationEntries> = {};
const listeners = new Set<() => void>();

export function initializeConfigurationEntries(initial: ConfigurationEntries) {
  configurationEntries = {
    "SMSC Accounts": configurationEntries["SMSC Accounts"] ?? initial["SMSC Accounts"],
    "Sender IDs": configurationEntries["Sender IDs"] ?? initial["Sender IDs"],
    Channels: configurationEntries.Channels ?? initial.Channels,
  };
}

export function replaceConfigurationEntries(entries: ConfigurationEntries) {
  configurationEntries = entries;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useConfigurationEntries(page: ConfigPage) {
  return useSyncExternalStore(
    subscribe,
    () => {
      const entries = configurationEntries[page];
      if (!entries) throw new Error(`Configuration entries for ${page} have not been initialized.`);
      return entries;
    },
    () => {
      const entries = configurationEntries[page];
      if (!entries) throw new Error(`Configuration entries for ${page} have not been initialized.`);
      return entries;
    },
  );
}

export function updateConfigurationEntries(
  page: ConfigPage,
  update: (entries: ConfigEntry[]) => ConfigEntry[],
) {
  const current = configurationEntries[page];
  if (!current) throw new Error(`Configuration entries for ${page} have not been initialized.`);

  const updated = update(current);
  configurationEntries[page] =
    page === "Channels"
      ? updated.map((entry) => ({
          ...entry,
          values: [
            entry.values[0] ?? "",
            entry.values[1] ?? "",
            `${entry.subscriberEmails.length} users`,
          ],
        }))
      : updated;
  listeners.forEach((listener) => listener());
}
