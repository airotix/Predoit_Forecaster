"""Explicit low-evidence estimates for newly observed articles/variants.

Only identities already exposed in the as-of order book are introduced here.
Article season codes are attributes, never a substitute for order dates.
An unobserved upcoming assortment still needs an explicit availability contract.
"""
import numpy as np
import pandas as pd
from forecasting import KEYS


def extend_launches(monthly,selection,raw,cutoff,as_of=None):
    if raw.empty:return monthly,selection,dict(newVariants=0,analogueVariants=0,bookedOnlyVariants=0)
    dates=pd.to_datetime(raw.Date_Commande,errors='coerce')
    permitted=dates.notna()
    if as_of is not None:permitted &= dates.dt.normalize()<=pd.Timestamp(as_of).normalize()
    observed=raw.loc[permitted].copy()
    known=set(map(tuple,monthly[KEYS].astype(str).drop_duplicates().to_numpy()))
    latest=observed.sort_values('Date_Commande').drop_duplicates(KEYS,keep='last')
    novel=latest[[tuple(str(r[k]) for k in KEYS) not in known for _,r in latest.iterrows()]]
    if novel.empty:return monthly,selection,dict(newVariants=0,analogueVariants=0,bookedOnlyVariants=0)
    past=observed[observed.year_month<=cutoff]
    recent=past[past.year_month>cutoff-12]
    facts=past.sort_values('Date_Commande').drop_duplicates('Reference',keep='last').set_index('Reference')
    active=set(recent.groupby('Reference').true_demand.sum().loc[lambda v:v>0].index)
    totals=monthly.groupby(['Reference','forecast_month'])[['forecast_conservative','forecast_base','forecast_optimistic']].sum()
    future_months=sorted(monthly.forecast_month.unique());rows=[];chosen=[];analogue_count=0
    existing_references=set(monthly.Reference)
    def text(row,column):
        value=row.get(column)
        return str(value).strip() if value is not None and pd.notna(value) else 'UNKNOWN'
    for reference,variants in novel.groupby('Reference'):
        first=variants.iloc[0];donors=[]
        if reference not in existing_references:
            for donor in sorted(active & set(totals.index.get_level_values(0))):
                if donor not in facts.index:continue
                fact=facts.loc[donor]
                if text(first,'Famille')!='UNKNOWN' and text(fact,'Famille')==text(first,'Famille') and text(fact,'Catalog_Brand')==text(first,'Catalog_Brand'):
                    donors.append(donor)
            material=[d for d in donors if text(facts.loc[d],'Matiere')==text(first,'Matiere')]
            if len(material)>=3:donors=material
        is_analogue=len(donors)>=3
        history=recent[recent.Reference.isin(donors)]
        size_counts=history.groupby('Taille').true_demand.sum().to_dict()
        colours=variants.Couleur.unique()
        weights={}
        for color,group in variants.groupby('Couleur'):
            counts={str(r.Taille):float(size_counts.get(r.Taille,0)) for _,r in group.iterrows()}
            denominator=sum(counts.values())
            for size,count in counts.items():weights[(str(color),size)]=count/denominator/len(colours) if denominator else 1/len(group)/len(colours)
        method='LAUNCH_ANALOGUE' if is_analogue else 'BOOKED_ONLY'
        reason='Uncalibrated category/brand analogue; pooled size curve and equal new-colour allocation require planner review.' if is_analogue else 'Newly observed identity has no independently validated forecast; shows known bookings only and requires assortment review.'
        for _,variant in variants.iterrows():
            key=tuple(str(variant[k]) for k in KEYS)
            chosen.append(dict(zip(KEYS,key),selected_model=method.lower(),validation_points=0,validation_absolute_error=None,baseline_absolute_error=None,
                calibration_points=0,calibration_wape=None,calibration_bias=None,confidence='LOW',confidence_reason=reason,needs_assortment_review=True,donor_articles=len(donors)))
            for month in future_months:
                donor_values=totals.loc[(donors,month),'forecast_base'] if is_analogue else []
                estimate=float(np.median(donor_values))*weights[(key[1],key[2])] if is_analogue else 0.
                rows.append(dict(zip(KEYS,key),forecast_month=month,forecast_conservative=0.,forecast_base=round(estimate,4),forecast_optimistic=round(estimate*2,4),
                    model_type=method,interval_method='UNCALIBRATED_LAUNCH',interval_samples=0))
            analogue_count+=int(is_analogue)
    return pd.concat([monthly,pd.DataFrame(rows)],ignore_index=True),pd.concat([selection,pd.DataFrame(chosen)],ignore_index=True),dict(newVariants=len(chosen),analogueVariants=analogue_count,bookedOnlyVariants=len(chosen)-analogue_count,
        notice='Only newly observed as-of identities are added. Unobserved future assortment is not inferred from article season codes. All launches require planner review.')
